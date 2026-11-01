"""Gene Heatmap Studio: upload, select columns, sort, choose Top N, and download PNG."""
import io
import hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, TwoSlopeNorm, LinearSegmentedColormap
import streamlit as st

st.set_page_config(page_title="Gene Heatmap Studio", page_icon="🧬", layout="wide")

PALETTES = {
    "Blues · recommended for magnitude": ("Blues", "sequential"),
    "Cividis · color-vision accessible": ("cividis", "sequential"),
    "Viridis · color-vision accessible": ("viridis", "sequential"),
    "YlGnBu · blue/green": ("YlGnBu", "sequential"),
    "Purples · single hue": ("Purples", "sequential"),
    "RdBu · signed fold changes": ("RdBu_r", "diverging"),
    "BrBG · signed values": ("BrBG", "diverging"),
}
EXAMPLE = pd.DataFrame({"Gene": ["HAC1", "HDA6", "HAT1", "GCN5", "HDA19"],
                        "Value": [1.80, -1.20, 0.65, 2.10, -0.85]})

st.markdown("""<style>
.block-container {max-width: 1500px; padding-top: 1.5rem;}
[data-testid="stSidebar"] {background-color: #f7f9fc;}
</style>""", unsafe_allow_html=True)
st.title("Gene Heatmap Studio")
st.caption("Upload a CSV, select two columns, sort and filter genes, customize your figure, then export a PNG.")

with st.sidebar:
    st.subheader("1 · Upload data")
    uploaded = st.file_uploader("Choose a CSV file", type="csv")
    with st.expander("Example CSV"):
        st.download_button("Download example CSV", EXAMPLE.to_csv(index=False).encode(),
                           file_name="example_genes.csv", mime="text/csv", use_container_width=True)

if uploaded is None:
    st.info("Upload a CSV using the sidebar to begin. No columns are selected automatically.")
    st.dataframe(EXAMPLE, hide_index=True)
    st.stop()

source_hash = hashlib.sha256(uploaded.getvalue()).hexdigest()
if st.session_state.get("source_hash") != source_hash:
    st.session_state["source_hash"] = source_hash
    st.session_state["generated_config"] = None
    for key in ("gene_column", "value_column"):
        st.session_state.pop(key, None)
try:
    df = pd.read_csv(io.BytesIO(uploaded.getvalue()), low_memory=False)
except Exception as exc:
    st.error(f"Could not read the CSV: {exc}")
    st.stop()
if len(df.columns) < 2:
    st.error("CSV must contain at least two columns.")
    st.stop()

with st.sidebar:
    st.success(f"Uploaded {uploaded.name} ({len(df):,} rows)")
    st.subheader("2 · Select columns")
    gene_col = st.selectbox("Gene / label column (text)", df.columns.tolist(), index=None,
                            placeholder="Select a column", key="gene_column")
    possible_numeric = [col for col in df.columns if col != gene_col and
                        pd.to_numeric(df[col], errors="coerce").notna().any()]
    value_col = st.selectbox("Value column (numeric)", possible_numeric, index=None,
                             placeholder="Select a column", key="value_column",
                             disabled=(gene_col is None))
if gene_col is None or value_col is None:
    st.info("Select a gene-name column and a numeric-value column in the sidebar.")
    with st.expander("Inspect uploaded CSV"):
        st.dataframe(df.head(20), hide_index=True, use_container_width=True)
    st.stop()

# Calculate valid, unique rows up front, so Top N can be limited to the available count.
preview_data = pd.DataFrame({"Gene": df[gene_col].astype("string").str.strip(),
                             "Value": pd.to_numeric(df[value_col], errors="coerce")})
valid = (preview_data["Gene"].notna() & preview_data["Gene"].ne("") &
         np.isfinite(preview_data["Value"].to_numpy(dtype=float, na_value=np.nan)))
preview_data = preview_data.loc[valid].copy()
if preview_data.empty:
    st.error("No valid gene / numeric value pairs. Try different columns.")
    st.stop()
unique_count = int(preview_data["Gene"].nunique())

with st.sidebar:
    st.subheader("3 · Arrange genes")
    with st.form("heatmap_form"):
        sort_mode = st.selectbox("Sort genes before plotting", [
            "Input order", "A to Z", "Z to A", "Value: low to high", "Value: high to low"
        ], index=1)
        duplicate_mode = st.selectbox("Repeated gene labels", [
            "Keep first", "Average values", "Stop with error"
        ])
        # Zero means all genes. Any positive N selects the first N after sorting.
        top_n = st.number_input(
            "Number of genes to show (Top N)", min_value=0,
            max_value=max(1, unique_count), value=0, step=1,
            help="Enter 0 for all genes, or a positive number for Top N after sorting."
        )
        st.caption("0 = all genes. Otherwise select the first N after sorting (e.g., lowest 10 values).")

        st.markdown("**Colors**")
        palette_name = st.selectbox("Scientific color palette", list(PALETTES), index=0)
        use_custom = st.checkbox("Use custom minimum and maximum colors", value=False)
        if use_custom:
            min_color = st.color_picker("Minimum color", "#F7FBFF")
            max_color = st.color_picker("Maximum color", "#08519C")
        else:
            min_color, max_color = "#F7FBFF", "#08519C"

        st.markdown("**Labels**")
        show_values = st.checkbox("Show numbers inside cells", value=True)
        decimals = st.slider("Decimal places", 0, 6, 2, disabled=not show_values)
        show_colorbar = st.checkbox("Show color legend", value=True)
        gene_font_size = st.slider("Gene name font size (pt)", 4, 60, 14)
        axis_font_size = st.slider("Column label font size (pt)", 4, 60, 14)
        value_font_size = st.slider("Cell value font size (pt)", 4, 60, 13,
                                    disabled=not show_values)
        legend_font_size = st.slider("Legend font size (pt)", 4, 50, 12,
                                     disabled=not show_colorbar)

        st.markdown("**Heatmap size**")
        # Width controls the actual colored heatmap cell (not just the overall canvas).
        cell_width = st.slider("Heatmap box width (inches)", 0.3, 15.0, 3.0, step=0.1)
        cell_height = st.slider("Heatmap box height per gene (inches)", 0.15, 3.0, 0.50, step=0.05)
        dpi = st.selectbox("PNG resolution", [150, 300, 600], index=1,
                           format_func=lambda x: f"{x} DPI")
        generate = st.form_submit_button("Generate heatmap", type="primary", use_container_width=True)

config = dict(source_hash=source_hash, gene_col=gene_col, value_col=value_col,
              sort_mode=sort_mode, duplicate_mode=duplicate_mode,
              top_n=int(top_n), palette_name=palette_name,
              use_custom=use_custom, min_color=min_color, max_color=max_color,
              show_values=show_values, decimals=decimals, show_colorbar=show_colorbar,
              gene_font_size=gene_font_size, axis_font_size=axis_font_size,
              value_font_size=value_font_size, legend_font_size=legend_font_size,
              cell_width=cell_width, cell_height=cell_height, dpi=dpi)
if generate:
    st.session_state["generated_config"] = config.copy()

cfg = st.session_state.get("generated_config")
if cfg and (cfg["source_hash"], cfg["gene_col"], cfg["value_col"]) != (source_hash, gene_col, value_col):
    st.session_state["generated_config"] = None
    cfg = None
if cfg is None:
    st.info("Choose sorting, Top N, colors, fonts, and cell dimensions in the sidebar, then click **Generate heatmap**.")
    with st.expander("Preview selected columns"):
        st.dataframe(df[[gene_col, value_col]].head(20), hide_index=True, use_container_width=True)
    st.stop()

clean = pd.DataFrame({"Gene": df[cfg["gene_col"]].astype("string").str.strip(),
                      "Value": pd.to_numeric(df[cfg["value_col"]], errors="coerce")})
mask = (clean["Gene"].notna() & clean["Gene"].ne("") &
        np.isfinite(clean["Value"].to_numpy(dtype=float, na_value=np.nan)))
removed = int((~mask).sum())
clean = clean.loc[mask].copy()
repeats = int(clean["Gene"].duplicated().sum())
if repeats:
    if cfg["duplicate_mode"] == "Stop with error":
        st.error(f"Found {repeats} repeated gene labels. Change the duplicate setting and regenerate.")
        st.stop()
    elif cfg["duplicate_mode"] == "Keep first":
        clean = clean.drop_duplicates("Gene", keep="first")
    else:
        clean = clean.groupby("Gene", sort=False, as_index=False)["Value"].mean()

if cfg["sort_mode"] == "A to Z":
    clean = clean.sort_values("Gene", key=lambda s: s.str.casefold(), kind="stable")
elif cfg["sort_mode"] == "Z to A":
    clean = clean.sort_values("Gene", key=lambda s: s.str.casefold(), ascending=False, kind="stable")
elif cfg["sort_mode"] == "Value: low to high":
    clean = clean.sort_values("Value", kind="stable")
elif cfg["sort_mode"] == "Value: high to low":
    clean = clean.sort_values("Value", ascending=False, kind="stable")

full_count = len(clean)
if cfg["top_n"] > 0:
    clean = clean.head(cfg["top_n"])  # Top N AFTER sorting for every mode
clean = clean.reset_index(drop=True)
values = clean["Value"].to_numpy(dtype=float)
labels = clean["Gene"].astype(str).tolist()
lo, hi = float(values.min()), float(values.max())
name, mode = PALETTES[cfg["palette_name"]]
cmap = (LinearSegmentedColormap.from_list("user_colors", [cfg["min_color"], cfg["max_color"]])
        if cfg["use_custom"] else matplotlib.colormaps[name])
if mode == "diverging" and not cfg["use_custom"]:
    extent = max(abs(lo), abs(hi), 1e-8)
    norm = TwoSlopeNorm(vmin=-extent, vcenter=0, vmax=extent)
else:
    norm = Normalize(vmin=lo, vmax=hi if hi > lo else lo + 1)

# Explicit axes coordinates make the COLOR BOX width match the user's setting.
# Reserve sufficient space for long gene names and large fonts.
label_chars = max(len(x) for x in labels)
left_margin = max(1.4, min(7.5, label_chars * cfg["gene_font_size"] / 80 + 0.75))
right_margin = 1.6 if cfg["show_colorbar"] else 0.5
bottom_margin = max(0.65, cfg["axis_font_size"] / 50 + 0.45)
top_margin = 0.3
box_w = cfg["cell_width"]
box_h = max(0.01, len(labels) * cfg["cell_height"])
fig_w = left_margin + box_w + right_margin
fig_h = bottom_margin + box_h + top_margin
fig = plt.figure(figsize=(fig_w, fig_h), facecolor="white")
ax = fig.add_axes([left_margin / fig_w, bottom_margin / fig_h,
                   box_w / fig_w, box_h / fig_h])
im = ax.imshow(values[:, None], aspect="auto", cmap=cmap, norm=norm,
               interpolation="nearest")
ax.set_yticks(range(len(labels)), labels=labels, fontsize=cfg["gene_font_size"])
ax.set_xticks([0], labels=[cfg["value_col"]], fontsize=cfg["axis_font_size"])
ax.tick_params(axis="both", which="major", length=0, pad=9)
for spine in ax.spines.values():
    spine.set_visible(False)
ax.set_xticks([-0.5, 0.5], minor=True)
ax.set_yticks(np.arange(-0.5, len(labels), 1), minor=True)
ax.grid(which="minor", color="white", linewidth=1.5)
ax.tick_params(which="minor", bottom=False, left=False)
if cfg["show_values"]:
    for i, value in enumerate(values):
        r, g, b, _ = cmap(norm(value))
        luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
        ax.text(0, i, f"{value:.{cfg['decimals']}f}", ha="center", va="center",
                fontsize=cfg["value_font_size"],
                color="#17212b" if luminance > 0.53 else "white")
if cfg["show_colorbar"]:
    cax = fig.add_axes([(left_margin + box_w + 0.25) / fig_w,
                        (bottom_margin + 0.05 * box_h) / fig_h,
                        0.22 / fig_w, 0.90 * box_h / fig_h])
    cb = fig.colorbar(im, cax=cax)
    cb.ax.tick_params(labelsize=cfg["legend_font_size"])
    cb.set_label(cfg["value_col"], fontsize=cfg["legend_font_size"])
    cb.outline.set_visible(False)

st.subheader("Heatmap preview")
st.caption(f"{cfg['sort_mode']} · Showing {len(clean):,} of {full_count:,} valid genes")
# Do not automatically stretch the preview; PNG retains the exact user-selected box dimensions.
st.pyplot(fig, use_container_width=False)
with st.expander("Selected genes and values"):
    st.dataframe(clean, hide_index=True, use_container_width=True)
if removed:
    st.warning(f"Excluded {removed} row(s) with missing/invalid labels or values.")

png_buffer = io.BytesIO()
fig.savefig(png_buffer, format="png", dpi=cfg["dpi"], facecolor="white")
plt.close(fig)
st.download_button("Download heatmap (PNG)", data=png_buffer.getvalue(),
                   file_name="gene_heatmap.png", mime="image/png", type="primary")
st.caption("Change the sidebar settings and click Generate heatmap again to refresh the plot.")
