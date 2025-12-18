
import streamlit as st
import pandas as pd
import plotly.express as px
import psycopg2
from psycopg2.extras import RealDictCursor
import config
import time

# --- Page Config ---
st.set_page_config(
    page_title="Orderly Bot Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Database Connection ---
@st.cache_resource
def get_connection():
    try:
        conn = psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            database=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD
        )
        return conn
    except Exception as e:
        st.error(f"Failed to connect to DB: {e}")
        return None

def fetch_data():
    conn = get_connection()
    if not conn: return pd.DataFrame()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM trade_logs ORDER BY timestamp DESC LIMIT 500;")
            data = cur.fetchall()
            df = pd.DataFrame(data)
            return df
    except Exception as e:
        st.error(f"Query failed: {e}")
        # Re-connect if connection lost
        return pd.DataFrame()

# --- Main Dashboard ---
st.title("🤖 Orderly Trading Bot Monitor")

# Auto-refresh toggle
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=True)

st.write("🔄 Fetching data...") # DEBUG
df = fetch_data()
st.write(f"✅ Data fetched. Rows: {len(df)}") # DEBUG

if df.empty:
    st.warning("No data found in trade_logs yet.")
    # Debug: why empty?
    st.write("Debug: DataFrame is empty.")
else:
    # --- Metrics Row ---
    col1, col2, col3, col4 = st.columns(4)
    
    total_signals = len(df)
    
    # Filter for executed trades (where status is OPEN or CLOSED_*)
    trades = df[df['status'].isin(['OPEN', 'CLOSED_TP', 'CLOSED_SL'])]
    total_trades = len(trades)
    
    # PnL Calculation
    realized_pnl = trades['pnl'].sum() if 'pnl' in trades.columns else 0.0
    win_count = len(trades[trades['pnl'] > 0])
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
    
    col1.metric("Total Signals", total_signals)
    col2.metric("Executed Trades", total_trades)
    col3.metric("Realized PnL (USDC)", f"${realized_pnl:.2f}", delta_color="normal")
    col4.metric("Win Rate", f"{win_rate:.1f}%")
    
    # --- Charts ---
    st.markdown("### 📈 Cumulative PnL")
    if not trades.empty and 'pnl' in trades.columns:
        trades_sorted = trades.sort_values('timestamp')
        trades_sorted['cum_pnl'] = trades_sorted['pnl'].cumsum()
        fig_pnl = px.line(trades_sorted, x='timestamp', y='cum_pnl', markers=True, title="Capital Growth")
        st.plotly_chart(fig_pnl, use_container_width=True)
    
    st.markdown("### 🚦 Recent AI Analysis")
    # Show last 20 logs including skipped ones
    st.dataframe(
        df[['timestamp', 'symbol', 'ai_action', 'ai_confidence', 'status', 'pnl', 'ai_reasoning']].head(20),
        use_container_width=True
    )
    
    # --- Advanced Stats ---
    st.markdown("### 📊 Performance by Token")
    if not trades.empty:
        pnl_by_token = trades.groupby('symbol')['pnl'].sum().reset_index()
        fig_bar = px.bar(pnl_by_token, x='symbol', y='pnl', color='pnl', title="PnL Distribution by Token")
        st.plotly_chart(fig_bar, use_container_width=True)


# --- Auto Refresh Handling ---
if auto_refresh:
    time.sleep(30)
    st.rerun()
