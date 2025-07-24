import streamlit as st
import pandas as pd
import altair as alt
import io
from sqlalchemy import create_engine
from streamlit_autorefresh import st_autorefresh

# Configurações iniciais da página
st.set_page_config(
    page_title="Dashboard de KPIs",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 Dashboard de KPIs Dinâmico")

# Sidebar: seleção da fonte de dados
st.sidebar.header("Fonte de Dados")
source = st.sidebar.selectbox(
    "Selecione a origem dos dados:",
    ["Arquivo CSV", "Arquivo Excel (.xlsx)", "Banco de Dados SQL"]
)

df = None
if source == "Arquivo CSV":
    uploaded_csv = st.sidebar.file_uploader("Envie o arquivo CSV", type=["csv"])
    if uploaded_csv:
        df = pd.read_csv(uploaded_csv)
elif source == "Arquivo Excel (.xlsx)":
    uploaded_xlsx = st.sidebar.file_uploader("Envie o arquivo Excel (.xlsx)", type=["xlsx"])
    if uploaded_xlsx:
        df = pd.read_excel(uploaded_xlsx)
elif source == "Banco de Dados SQL":
    db_type = st.sidebar.selectbox("Tipo de banco de dados", ["postgresql", "mysql", "sqlite"])
    engine = None
    if db_type == "sqlite":
        sqlite_path = st.sidebar.text_input("Caminho do arquivo SQLite (.db)")
        if sqlite_path:
            engine = create_engine(f"sqlite:///{sqlite_path}")
    else:
        db_user = st.sidebar.text_input("Usuário")
        db_pass = st.sidebar.text_input("Senha", type="password")
        db_host = st.sidebar.text_input("Host", value="localhost")
        db_port = st.sidebar.text_input(
            "Porta", value="5432" if db_type == "postgresql" else "3306"
        )
        db_name = st.sidebar.text_input("Database")
        if all([db_user, db_pass, db_host, db_port, db_name]):
            engine = create_engine(
                f"{db_type}://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
            )
    query = st.sidebar.text_area("Digite a tabela ou consulta SQL")
    if engine and query:
        df = pd.read_sql_query(query, engine)

if df is not None:
    # Widgets dinâmicos
    cols = df.columns.tolist()
    date_col = st.sidebar.selectbox("Coluna de data", options=cols)
    num_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    value_col = st.sidebar.selectbox("Coluna de valor (KPI)", options=num_cols)
    group_cols = st.sidebar.multiselect(
        "Dimensões para agrupar (ex: região, cidade)",
        options=[c for c in cols if c not in [date_col, value_col]]
    )
    refresh_interval = st.sidebar.number_input(
        "Intervalo de atualização (segundos)",
        min_value=1,
        value=10
    )

    # Auto-refresh do app
    count = st_autorefresh(interval=refresh_interval * 1000, limit=None)

    @st.cache_data
    def get_data():
        df_copy = df.copy()
        df_copy[date_col] = pd.to_datetime(df_copy[date_col])
        return df_copy

    data = get_data()

    # Cálculo de KPIs
    total = data[value_col].sum()
    mean = data[value_col].mean()
    sorted_data = data.sort_values(date_col)
    latest = sorted_data.iloc[-1][value_col]
    prev = sorted_data.iloc[-2][value_col] if len(sorted_data) > 1 else latest
    delta = latest - prev

    k1, k2, k3 = st.columns(3)
    k1.metric("Total acumulado", f"{total:,.2f}")
    k2.metric("Média", f"{mean:,.2f}")
    k3.metric("Última variação", f"{latest:,.2f}", f"{delta:+.2f}")

    # Gráfico de linha
    st.markdown("### Evolução do KPI ao longo do tempo")
    line = (
        alt.Chart(data)
        .mark_line(point=True)
        .encode(
            x=alt.X(date_col, title="Data"),
            y=alt.Y(value_col, title="Valor"),
            tooltip=[date_col, value_col]
        )
        .properties(width="container", height=300)
    )
    st.altair_chart(line, use_container_width=True)

    # Ranking por dimensão
    if group_cols:
        st.markdown(f"### Top 10 por dimensão: {group_cols[0]}")
        agg = (
            data.groupby(group_cols)[value_col]
            .sum()
            .reset_index()
            .sort_values(value_col, ascending=False)
            .head(10)
        )
        bar = (
            alt.Chart(agg)
            .mark_bar()
            .encode(
                x=alt.X(value_col, title="Total"),
                y=alt.Y(f"{group_cols[0]}:N", sort='-x', title=group_cols[0]),
                tooltip=group_cols + [value_col]
            )
            .properties(width="container", height=300)
        )
        st.altair_chart(bar, use_container_width=True)

    # Geração de relatório
    st.markdown("---")
    st.markdown("## Gerar relatório de KPIs")

    def generate_report(df_report: pd.DataFrame) -> bytes:
        buf = io.BytesIO()
        # Usa contexto para fechar automaticamente o writer
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            # Planilha de dados brutos
            df_report.to_excel(writer, sheet_name="Dados", index=False)
            # Planilha de resumo
            summary = {
                "Total acumulado": total,
                "Média": mean,
                "Última leitura": latest,
                "Variação": delta
            }
            summary_df = pd.DataFrame.from_dict(summary, orient="index", columns=["Valor"]).reset_index()
            summary_df.columns = ["Métrica", "Valor"]
            summary_df.to_excel(writer, sheet_name="KPIs", index=False)
        # Pega bytes do buffer
        return buf.getvalue()

    report_bytes = generate_report(data)
    st.download_button(
        label="📥 Baixar relatório (Excel)",
        data=report_bytes,
        file_name="relatorio_kpis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.info("Aguardando a seleção e carregamento da fonte de dados...")
