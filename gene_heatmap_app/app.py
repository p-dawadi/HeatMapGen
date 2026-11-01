"""Gene Heatmap Studio: upload -> map -> configure -> generate -> PNG."""
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
.block-container {max-width: 1280px; padding-top: 2rem;}
[data-testid="stSidebar"] {background-color: #f7f9fc;}
div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] {font-weight: 650;}
</style>""", unsafe_allow_html=True)

st.title("Gene Heatmap Studio")
st.caption("Create a publication-ready heatmap in four simple steps.")

with st.sidebar:
    st.subheader("1 · Upload data")
    uploaded = st.file_uploader("Choose a CSV file", type=["csv"],
                                help="Your CSV must contain a label/text column and a numeric column.")
    with st.expander("Need an example CSV?"):
        st.download_button("Download example CSV", EXAMPLE.to_csv(index=False).encode("utf-8"),
                           "example_genes.csv", mime="text/csv", use_container_width=True)

if uploaded is None:
    st.info("Start by uploading a CSV file using the panel on the left.")
    st.markdown("**Your file should contain two columns, for example:**")
    st.dataframe(EXAMPLE, hide_index=True, use_container_width=False)
    st.caption("After upload, you'll select the label and value columns. Nothing is selected automatically, and no heatmap is created yet.")
    st.stop()

source_hash = hashlib.sha256(uploaded.getvalue()).hexdigest()
if st.session_state.get("source_hash") != source_hash:
    st.session_state["source_hash"] = source_hash
    st.session_state["generated_config"] = None
    # Reset both selectors so no column is preselected for a new upload.
    for key in ("gene_column", "value_column"):
        st.session_state.pop(key, None)

try:
    df = pd.read_csv(io.BytesIO(uploaded.getvalue()), low_memory=False)
except Exception as exc:
    st.error(f"Could not read this CSV: {exc}")
    st.stop()
if df.shape[1] < 2:
    st.error("Please upload a CSV with at least two columns.")
    st.stop()

with st.sidebar:
    st.success(f"Uploaded: {uploaded.name} · {len(df):,} rows")
    st.subheader("2 · Choose columns")
    columns = df.columns.tolist()
    gene_col = st.selectbox("Gene / label column (text)", columns, index=None,
                            placeholder="Select a text column…", key="gene_column")
    numeric_cols = [c for c in columns if c != gene_col and pd.to_numeric(df[c], errors="coerce").notna().any()]
    value_col = st.selectbox("Value column (numeric)", numeric_cols, index=None,
                             placeholder="Select a numeric column…", key="value_column",
                             disabled=gene_col is None)

if gene_col is None or value_col is None:
    st.subheader("Select your columns")
    st.info("Use the two dropdowns on the left to select a text label column and a numeric value column. Both selections are required.")
    with st.expander("Inspect uploaded CSV", expanded=False):
        st.dataframe(df.head(20), use_container_width=True, hide_index=True)
    st.stop()

with st.sidebar:
    st.subheader("3 · Customize")
    with st.form("plot_settings", border=False):
        st.markdown("**Gene order**")
        sort_mode = st.selectbox("Sort genes before plotting",
            ["Input order", "A to Z", "Z to A", "Value: low to high", "Value: high to low"],
            index=1)
        duplicate_mode = st.selectbox("Repeated labels", ["Keep first", "Average values", "Stop with error"])

        st.markdown("**Colors**")
        palette_name = st.selectbox("Scientific palette", list(PALETTES), index=0)
        use_custom = st.checkbox("Use custom minimum and maximum colors", value=False)
        if use_custom:
            min_color = st.color_picker("Minimum color", "#F7FBFF")
            max_color = st.color_picker("Maximum color", "#08519C")
            st.caption("The minimum and maximum colors override the preset palette.")
        else:
            min_color, max_color = "#F7FBFF", "#08519C"

        st.markdown("**Labels and appearance**")
        show_values = st.checkbox("Show values in cells", value=True)
        decimals = st.slider("Decimal places", 0, 4, 2, disabled=not show_values)
        show_colorbar = st.checkbox("Show color scale", value=True)
        st.caption("Adjust each text element independently for the exported figure.")
        gene_font_size = st.slider("Gene name font size", 6, 28, 12)
        axis_font_size = st.slider("Column label font size", 6, 28, 12)
        value_font_size = st.slider("Cell value font size", 6, 28, 12, disabled=not show_values)
        legend_font_size = st.slider("Color legend font size", 6, 24, 11, disabled=not show_colorbar)
        row_height = st.slider("Cell height", 0.25, 0.8, 0.48, 0.01)
        dpi = st.selectbox("PNG quality", [300, 600], index=0, format_func=lambda x: f"{x} DPI")
        generate = st.form_submit_button("Generate heatmap", type="primary", use_container_width=True)

config = dict(source_hash=source_hash, gene_col=gene_col, value_col=value_col,
              sort_mode=sort_mode, duplicate_mode=duplicate_mode, palette_name=palette_name,
              use_custom=use_custom, min_color=min_color, max_color=max_color,
              show_values=show_values, decimals=decimals, show_colorbar=show_colorbar,
              gene_font_size=gene_font_size, axis_font_size=axis_font_size,
              value_font_size=value_font_size, legend_font_size=legend_font_size,
              row_height=row_height, dpi=dpi)
if generate:
    st.session_state["generated_config"] = config.copy()

# All controls take effect only upon explicit Generate; a changed column selection
# invalidates the old plot until the user confirms the new configuration.
saved = st.session_state.get("generated_config")
if saved and (saved["source_hash"], saved["gene_col"], saved["value_col"]) != (source_hash, gene_col, value_col):
    st.session_state["generated_config"] = None
    saved = None

st.subheader("Ready to generate")
st.caption(f"File: {uploaded.name}  ·  Label: {gene_col}  ·  Values: {value_col}")
if not saved:
    st.info("Choose gene order, color palette, and label options in the sidebar; then click **Generate heatmap**.")
    with st.expander("Preview source data", expanded=False):
        st.dataframe(df[[gene_col, value_col]].head(20), use_container_width=True, hide_index=True)
    st.stop()

# Use the last submitted settings for all calculations and exports.
cfg = saved
clean = pd.DataFrame({"Gene": df[cfg["gene_col"]].astype("string").str.strip(),
                      "Value": pd.to_numeric(df[cfg["value_col"]], errors="coerce")})
valid = clean["Gene"].notna() & clean["Gene"].ne("") & np.isfinite(clean["Value"].fillna(np.nan))
removed = int((~valid).sum())
clean = clean.loc[valid].copy()
if clean.empty:
    st.error("No valid gene/value rows. Please choose different columns or correct the file.")
    st.stop()
repeats = int(clean["Gene"].duplicated().sum())
if repeats:
    if cfg["duplicate_mode"] == "Stop with error":
        st.error(f"Found {repeats} duplicate gene label(s). Select a duplicate-handling option and regenerate.")
        st.stop()
    if cfg["duplicate_mode"] == "Keep first":
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

values = clean["Value"].to_numpy(dtype=float)
labels = clean["Gene"].astype(str).tolist()
lo, hi = float(values.min()), float(values.max())
name, mode = PALETTES[cfg["palette_name"]]
cmap = (LinearSegmentedColormap.from_list("custom", [cfg["min_color"], cfg["max_color"]])
        if cfg["use_custom"] else matplotlib.colormaps[name])
if mode == "diverging" and not cfg["use_custom"]:
    extent = max(abs(lo), abs(hi), 1e-8)
    norm = TwoSlopeNorm(vmin=-extent, vcenter=0, vmax=extent)
else:
    norm = Normalize(vmin=lo, vmax=hi if hi > lo else lo + 1)

height = max(2.7, 1.1 + len(labels) * cfg["row_height"])
fig, ax = plt.subplots(figsize=(5.3 + (1 if cfg["show_colorbar"] else 0), height), constrained_layout=True)
fig.patch.set_facecolor("white")
im = ax.imshow(values.reshape(-1, 1), aspect="auto", cmap=cmap, norm=norm, interpolation="nearest")
ax.set_yticks(np.arange(len(labels)), labels=labels, fontsize=cfg["gene_font_size"])
ax.set_xticks([0], [cfg["value_col"]], fontsize=cfg["axis_font_size"])
ax.tick_params(axis="both", length=0, pad=8)
for spine in ax.spines.values():
    spine.set_visible(False)
ax.set_xticks([-.5, .5], minor=True)
ax.set_yticks(np.arange(-.5, len(labels), 1), minor=True)
ax.grid(which="minor", color="white", linewidth=1.5)
ax.tick_params(which="minor", left=False, bottom=False)
if cfg["show_values"]:
    for i, value in enumerate(values):
        r, g, b, _ = cmap(norm(value))
        luminance = .2126*r + .7152*g + .0722*b
        ax.text(0, i, f"{value:.{cfg['decimals']}f}", ha="center", va="center",
                color="#17212b" if luminance > .53 else "white", fontsize=cfg["value_font_size"])
if cfg["show_colorbar"]:
    cb = fig.colorbar(im, ax=ax, fraction=.075, pad=.08, shrink=.9)
    cb.set_label(cfg["value_col"], fontsize=cfg["legend_font_size"])
    cb.ax.tick_params(labelsize=cfg["legend_font_size"])
    cb.outline.set_visible(False)

left, right = st.columns([3.5, 1], gap="large")
with left:
    st.subheader("Heatmap preview")
    st.pyplot(fig, use_container_width=True)
with right:
    st.subheader("Summary")
    st.metric("Genes", f"{len(clean):,}")
    st.metric("Minimum", f"{lo:.2f}")
    st.metric("Maximum", f"{hi:.2f}")
    if removed:
        st.warning(f"{removed} row(s) excluded: invalid or missing values.")
    with st.expander("View sorted values"):
        st.dataframe(clean.reset_index(drop=True), hide_index=True, use_container_width=True)

buf = io.BytesIO()
fig.savefig(buf, format="png", dpi=cfg["dpi"], bbox_inches="tight", facecolor="white")
plt.close(fig)
st.download_button("Download heatmap · PNG", data=buf.getvalue(), file_name="gene_heatmap.png",
                   mime="image/png", type="primary")
st.caption("To change settings, make your selections in the sidebar and click Generate heatmap again.")
