"""Gene Heatmap Studio — compact publication-style single-column heatmaps."""
import io
import hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, TwoSlopeNorm, LinearSegmentedColormap
import streamlit as st

st.set_page_config(page_title='Gene Heatmap Studio', page_icon='🧬', layout='wide')

PALETTES = {
    'Blues · sequential': ('Blues', 'sequential'),
    'Cividis · accessible': ('cividis', 'sequential'),
    'Viridis · accessible': ('viridis', 'sequential'),
    'YlGnBu · sequential': ('YlGnBu', 'sequential'),
    'Purples · sequential': ('Purples', 'sequential'),
    'RdBu · signed values': ('RdBu_r', 'diverging'),
    'BrBG · signed values': ('BrBG', 'diverging'),
}
EXAMPLE = pd.DataFrame({
    'Gene': ['HAC1', 'HDA6', 'HAT1', 'GCN5', 'HDA19'],
    'Value': [1.80, -1.20, 0.65, 2.10, -0.85],
})

st.markdown('''<style>
.block-container {max-width: 1400px; padding-top: 1.3rem;}
[data-testid="stSidebar"] {background: #f7f9fc;}
</style>''', unsafe_allow_html=True)
st.title('Gene Heatmap Studio')
st.caption('Create compact, publication-ready single-column heatmaps from your CSV.')

with st.sidebar:
    st.subheader('1 · Upload CSV')
    uploaded = st.file_uploader('Choose CSV', type=['csv'])
    with st.expander('Example CSV'):
        st.download_button('Download example CSV', EXAMPLE.to_csv(index=False).encode('utf-8'),
                           'example_genes.csv', 'text/csv', use_container_width=True)

if uploaded is None:
    st.info('Upload a CSV to begin. Column selectors and plotting options appear after upload.')
    st.stop()

source_hash = hashlib.sha256(uploaded.getvalue()).hexdigest()
if st.session_state.get('source_hash') != source_hash:
    st.session_state['source_hash'] = source_hash
    st.session_state['generated_config'] = None
    for key in ('gene_column', 'value_column'):
        st.session_state.pop(key, None)
try:
    df = pd.read_csv(io.BytesIO(uploaded.getvalue()), low_memory=False)
except Exception as exc:
    st.error(f'Cannot read CSV: {exc}')
    st.stop()
if df.shape[1] < 2:
    st.error('CSV needs at least two columns.')
    st.stop()

with st.sidebar:
    st.success(f'{uploaded.name} · {len(df):,} rows')
    st.subheader('2 · Select columns')
    gene_col = st.selectbox('Gene / label column', df.columns.tolist(), index=None,
                            placeholder='Select text column', key='gene_column')
    possible_numeric = [c for c in df.columns if c != gene_col and
                        pd.to_numeric(df[c], errors='coerce').notna().any()]
    value_col = st.selectbox('Numeric value column', possible_numeric, index=None,
                             placeholder='Select numeric column', key='value_column',
                             disabled=gene_col is None)

if gene_col is None or value_col is None:
    st.info('Select one gene-label column and one numeric-value column in the sidebar.')
    with st.expander('Inspect uploaded CSV'):
        st.dataframe(df.head(20), hide_index=True)
    st.stop()

base = pd.DataFrame({'Gene': df[gene_col].astype('string').str.strip(),
                     'Value': pd.to_numeric(df[value_col], errors='coerce')})
mask = (base['Gene'].notna() & base['Gene'].ne('') &
        np.isfinite(base['Value'].to_numpy(dtype=float, na_value=np.nan)))
base = base.loc[mask].copy()
if base.empty:
    st.error('No rows contain both a gene label and numeric value.')
    st.stop()

with st.sidebar:
    with st.form('plot_settings'):
        st.subheader('3 · Sort and select')
        sort_mode = st.selectbox('Sort genes before plotting',
            ['Input order', 'A to Z', 'Z to A', 'Value: low to high', 'Value: high to low'],
            index=1)
        duplicate_mode = st.selectbox('Repeated gene labels',
            ['Keep first', 'Average values', 'Stop with error'])
        top_n = st.number_input('Top N genes (0 = all)', min_value=0,
                                max_value=int(len(base)), value=0, step=1)
        st.caption('Top N is applied after the selected sorting method.')

        st.subheader('4 · Colors')
        palette_name = st.selectbox('Scientific palette', list(PALETTES), index=0)
        use_custom = st.checkbox('Use custom minimum / median / maximum colors')
        if use_custom:
            min_color = st.color_picker('Minimum color (lowest value)', '#F7FBFF')
            median_color = st.color_picker('Median color (middle value)', '#9ECAE1')
            max_color = st.color_picker('Maximum color (highest value)', '#08519C')
            st.caption('The median color is assigned to the statistical median of the displayed gene values.')
        else:
            min_color, median_color, max_color = '#F7FBFF', '#9ECAE1', '#08519C'

        st.subheader('5 · Layout')
        box_width = st.slider('Colored heatmap width (inches)', 0.15, 10.0, 1.1, 0.05)
        row_height = st.slider('Height per gene (inches)', 0.05, 1.5, 0.20, 0.01)
        gap = st.slider('Gap between gene rows (points)', 0.0, 3.0, 0.0, 0.25)
        show_column_label = st.checkbox('Show column label below heatmap', value=False)
        show_values = st.checkbox('Show values inside cells', value=False)
        decimals = st.slider('Decimal places', 0, 6, 2, disabled=not show_values)
        gene_font = st.slider('Gene label font (pt)', 4, 60, 10)
        # Column and in-cell value labels use consistent automatic sizes.
        col_font = gene_font
        value_font = min(gene_font, 12)

        st.subheader('6 · Legend and export')
        legend_position = st.selectbox('Legend position', ['Right', 'Bottom', 'Hide'], index=0)
        legend_length = st.slider('Legend length (% of heatmap)', 10, 100, 45, 5,
                                  disabled=legend_position == 'Hide')
        legend_thickness = st.slider('Legend thickness (inches)', 0.05, 0.60, 0.12, 0.01,
                                     disabled=legend_position == 'Hide')
        legend_gap = st.slider('Distance from heatmap to legend (inches)',
                               0.02, 2.00, 0.12, 0.01,
                               disabled=legend_position == 'Hide',
                               help='Controls the gap between the colored heatmap and its legend, whether below or on the right.')
        legend_font = st.slider('Legend font (pt)', 4, 50, 9,
                                disabled=legend_position == 'Hide')
        legend_title = st.checkbox('Show legend title', value=False,
                                   disabled=legend_position == 'Hide')
        dpi = st.selectbox('PNG resolution', [300, 600], index=0,
                           format_func=lambda x: f'{x} DPI')
        generate = st.form_submit_button('Generate heatmap', type='primary', use_container_width=True)

cfg_now = dict(source_hash=source_hash, gene_col=gene_col, value_col=value_col,
               sort_mode=sort_mode, duplicate_mode=duplicate_mode, top_n=int(top_n),
               palette_name=palette_name, use_custom=use_custom,
               min_color=min_color, median_color=median_color, max_color=max_color, box_width=box_width,
               row_height=row_height, gap=gap, show_column_label=show_column_label,
               show_values=show_values, decimals=decimals, gene_font=gene_font,
               col_font=col_font, value_font=value_font,
               legend_position=legend_position, legend_length=legend_length,
               legend_thickness=legend_thickness, legend_gap=legend_gap, legend_font=legend_font,
               legend_title=legend_title, dpi=dpi)
if generate:
    st.session_state['generated_config'] = cfg_now.copy()
cfg = st.session_state.get('generated_config')
if cfg is not None and (cfg['source_hash'], cfg['gene_col'], cfg['value_col']) != (source_hash, gene_col, value_col):
    cfg = None
    st.session_state['generated_config'] = None
if cfg is None:
    st.info('Adjust sorting, size, and colors, then click **Generate heatmap**.')
    st.stop()

clean = base.copy()
repeats = int(clean['Gene'].duplicated().sum())
if repeats:
    if cfg['duplicate_mode'] == 'Stop with error':
        st.error(f'{repeats} repeated labels found. Change duplicate handling and generate again.')
        st.stop()
    elif cfg['duplicate_mode'] == 'Keep first':
        clean = clean.drop_duplicates('Gene', keep='first')
    else:
        clean = clean.groupby('Gene', sort=False, as_index=False)['Value'].mean()

if cfg['sort_mode'] == 'A to Z':
    clean = clean.sort_values('Gene', key=lambda s: s.str.casefold(), kind='stable')
elif cfg['sort_mode'] == 'Z to A':
    clean = clean.sort_values('Gene', key=lambda s: s.str.casefold(), ascending=False, kind='stable')
elif cfg['sort_mode'] == 'Value: low to high':
    clean = clean.sort_values('Value', kind='stable')
elif cfg['sort_mode'] == 'Value: high to low':
    clean = clean.sort_values('Value', ascending=False, kind='stable')
all_count = len(clean)
if cfg['top_n']:
    clean = clean.head(cfg['top_n'])
clean = clean.reset_index(drop=True)
values = clean['Value'].to_numpy(float)
labels = clean['Gene'].astype(str).tolist()
low, high = float(values.min()), float(values.max())
name, palette_type = PALETTES[cfg['palette_name']]
# Map the chosen middle color to the actual median, not just an arbitrary center.
# Avoid duplicate color stops when the median equals an extreme.
if cfg['use_custom']:
    median_value = float(np.median(values))
    if high > low:
        median_fraction = (median_value - low) / (high - low)
        if median_fraction <= 0:
            stops = [(0.0, cfg['median_color']), (1.0, cfg['max_color'])]
        elif median_fraction >= 1:
            stops = [(0.0, cfg['min_color']), (1.0, cfg['median_color'])]
        else:
            stops = [(0.0, cfg['min_color']),
                     (median_fraction, cfg['median_color']),
                     (1.0, cfg['max_color'])]
    else:
        stops = [(0.0, cfg['median_color']), (1.0, cfg['median_color'])]
    cmap = LinearSegmentedColormap.from_list('custom', stops, N=256)
else:
    cmap = matplotlib.colormaps[name]
if palette_type == 'diverging' and not cfg['use_custom']:
    span = max(abs(low), abs(high), 1e-9)
    norm = TwoSlopeNorm(vmin=-span, vcenter=0, vmax=span)
else:
    norm = Normalize(vmin=low, vmax=high if high > low else low + 1)

# Exact physical dimensions: colored heatmap width and each gene-row height.
# Colorbar is separately sized and does not stretch to the full heatmap height.
n = len(labels)
heat_w = cfg['box_width']
heat_h = max(0.05, n * cfg['row_height'])
max_label_len = max(len(s) for s in labels)
left = max(0.8, min(7.0, max_label_len * cfg['gene_font'] * 0.009 + 0.40))
top = 0.18
bottom = 0.50 if cfg['show_column_label'] else 0.16
right = 0.20 if cfg['legend_position'] != 'Right' else (
    cfg['legend_gap'] + cfg['legend_thickness'] + max(0.50, cfg['legend_font'] * 0.075 + 0.25)
)
if cfg['legend_position'] == 'Bottom':
    # Include physical bar gap + thickness + tick-label/title clearance below it.
    # The legend gap is measured from the colored heatmap's lower edge.
    bottom += cfg['legend_gap'] + cfg['legend_thickness'] + max(
        0.30, cfg['legend_font'] * 0.025 + (0.18 if cfg['legend_title'] else 0.08)
    )
fw, fh = left + heat_w + right, top + heat_h + bottom
fig = plt.figure(figsize=(fw, fh), facecolor='white')
ax = fig.add_axes([left/fw, bottom/fh, heat_w/fw, heat_h/fh])
im = ax.imshow(values.reshape(-1, 1), aspect='auto', interpolation='nearest', cmap=cmap, norm=norm)
ax.set_yticks(np.arange(n), labels=labels, fontsize=cfg['gene_font'])
ax.set_xticks([0] if cfg['show_column_label'] else [],
              [cfg['value_col']] if cfg['show_column_label'] else [], fontsize=cfg['col_font'])
ax.tick_params(axis='both', which='both', length=0, pad=3)
for spine in ax.spines.values():
    spine.set_visible(False)
# Separators optional; default 0 creates fully contiguous strips.
if cfg['gap'] > 0:
    for y in np.arange(0.5, n, 1):
        ax.axhline(y, color='white', linewidth=cfg['gap'])
if cfg['show_values']:
    for i, v in enumerate(values):
        r, g, b, _ = cmap(norm(v))
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        ax.text(0, i, f"{v:.{cfg['decimals']}f}", ha='center', va='center',
                fontsize=cfg['value_font'], color='#111827' if lum > .52 else 'white')

if cfg['legend_position'] != 'Hide':
    length = cfg['legend_length'] / 100
    thick = cfg['legend_thickness']
    if cfg['legend_position'] == 'Right':
        legend_h = heat_h * length
        x0 = left + heat_w + cfg['legend_gap']
        y0 = bottom + (heat_h - legend_h) / 2
        cax = fig.add_axes([x0/fw, y0/fh, thick/fw, legend_h/fh])
        cb = fig.colorbar(im, cax=cax, orientation='vertical')
    else:
        legend_w = heat_w * length
        x0 = left + (heat_w - legend_w) / 2
        y0 = bottom - cfg['legend_gap'] - thick
        cax = fig.add_axes([x0/fw, y0/fh, legend_w/fw, thick/fh])
        cb = fig.colorbar(im, cax=cax, orientation='horizontal')
    cb.ax.tick_params(labelsize=cfg['legend_font'], length=2, pad=2)
    cb.outline.set_visible(False)
    if cfg['legend_title']:
        cb.set_label(cfg['value_col'], fontsize=cfg['legend_font'], labelpad=3)

st.subheader('Heatmap preview')
st.caption(f"{cfg['sort_mode']} · Showing {n} of {all_count} genes · {cfg['row_height']:.2f} in per row · No row gaps by default")
st.pyplot(fig, use_container_width=False)
with st.expander('View selected gene values'):
    st.dataframe(clean, hide_index=True, use_container_width=True)

png = io.BytesIO()
fig.savefig(png, dpi=cfg['dpi'], format='png', facecolor='white')
plt.close(fig)
st.download_button('Download high-resolution PNG', data=png.getvalue(),
                   file_name='gene_heatmap.png', mime='image/png', type='primary')
st.caption('Change sidebar settings and click Generate heatmap again to refresh the figure.')
