"""
dashboard.py - 実戦成績ダッシュボード

使い方:
  streamlit run dashboard.py

機能:
  - 累積成績推移グラフ
  - グレード別ROI分析
  - 戦略別パフォーマンス比較
  - 単勝/複勝/馬連/3連複の的中率推移
  - レース別詳細記録
"""
import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go


LOG_FILE = Path(__file__).parent / 'data' / 'daily_results_log.json'


# ============================================================
# データロード
# ============================================================

@st.cache_data(ttl=60)
def load_log():
    if not LOG_FILE.exists():
        return None
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def races_to_df(log):
    """全レースを単一DataFrameに展開"""
    rows = []
    for day in log['days']:
        for r in day['races']:
            row = dict(r)
            row['date'] = day['date']
            row['model'] = day.get('model', 'v0.7')
            rows.append(row)
    df = pd.DataFrame(rows)
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
    return df


# ============================================================
# ページ設定
# ============================================================

st.set_page_config(
    page_title="競馬AI 実戦成績ダッシュボード",
    page_icon="🏇",
    layout="wide",
)

st.title("🏇 競馬AI 実戦成績ダッシュボード")
st.caption(f"最終更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# データロード
log = load_log()

if not log or not log.get('days'):
    st.warning("まだ記録がありません。`log_daily_results.py` で記録してください。")
    st.code("python log_daily_results.py result.csv --date 2026-05-16")
    st.stop()

df = races_to_df(log)
all_dates = sorted(df['date'].dt.strftime('%Y-%m-%d').unique())

# ============================================================
# サイドバー: フィルタ
# ============================================================

st.sidebar.header("🔍 フィルタ")

# 日付範囲
date_range = st.sidebar.date_input(
    "期間",
    value=(df['date'].min(), df['date'].max()),
    min_value=df['date'].min(),
    max_value=df['date'].max(),
)

# グレード
grades = st.sidebar.multiselect(
    "グレード",
    options=sorted(df['grade'].unique()),
    default=sorted(df['grade'].unique()),
)

# モデル
models = st.sidebar.multiselect(
    "モデル",
    options=sorted(df['model'].unique()),
    default=sorted(df['model'].unique()),
)

# 場所
places = st.sidebar.multiselect(
    "競馬場",
    options=sorted(df['place'].dropna().unique()),
    default=sorted(df['place'].dropna().unique()),
)

# フィルタ適用
if len(date_range) == 2:
    mask = (df['date'].dt.date >= date_range[0]) & (df['date'].dt.date <= date_range[1])
    df = df[mask]
df = df[df['grade'].isin(grades) & df['model'].isin(models) & df['place'].isin(places)]

if df.empty:
    st.warning("フィルタ条件に該当するレースなし")
    st.stop()


# ============================================================
# KPI ヘッダー
# ============================================================

st.header("📊 累計KPI")

n = len(df)
win_n = df['hit_win'].sum()
place_n = df['hit_place'].sum()
qui_n = df['hit_quinella'].sum()
trio_n = df['hit_trio_box'].sum()

# 単勝ROI計算
df['win_pay'] = df.apply(
    lambda r: r['ai_top1_odds'] * 100 if r['hit_win'] and pd.notna(r['ai_top1_odds']) else 0,
    axis=1
)
bet_total = n * 100
payout_total = df['win_pay'].sum()
roi = payout_total / bet_total * 100 if bet_total else 0
pnl = payout_total - bet_total

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("総レース数", f"{n}")
col2.metric("AI ◎ 単勝", f"{win_n/n*100:.1f}%", f"{win_n}/{n}")
col3.metric("AI ◎ 複勝", f"{place_n/n*100:.1f}%", f"{place_n}/{n}")
col4.metric("単勝ROI", f"{roi:.1f}%", f"{pnl:+,.0f}円")
col5.metric("3連複的中", f"{trio_n/n*100:.1f}%", f"{trio_n}/{n}")


# ============================================================
# タブ
# ============================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 推移",
    "🎯 グレード別",
    "💰 戦略別ROI",
    "🏇 詳細記録",
    "📋 全レース"
])


# ============================================================
# タブ1: 推移
# ============================================================

with tab1:
    st.subheader("日別の的中率と ROI")
    
    daily = df.groupby(df['date'].dt.date).agg(
        race_count=('race_no', 'count'),
        hit_win=('hit_win', 'sum'),
        hit_place=('hit_place', 'sum'),
        hit_quinella=('hit_quinella', 'sum'),
        hit_trio=('hit_trio_box', 'sum'),
        bet=('race_no', lambda x: len(x) * 100),
        payout=('win_pay', 'sum'),
    ).reset_index()
    daily['date'] = pd.to_datetime(daily['date'])
    daily['win_rate'] = daily['hit_win'] / daily['race_count'] * 100
    daily['place_rate'] = daily['hit_place'] / daily['race_count'] * 100
    daily['roi'] = daily['payout'] / daily['bet'] * 100
    daily['cumulative_pnl'] = (daily['payout'] - daily['bet']).cumsum()
    daily['cumulative_roi'] = daily['payout'].cumsum() / daily['bet'].cumsum() * 100
    
    # 的中率推移
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily['date'], y=daily['win_rate'],
        mode='lines+markers', name='単勝的中率', line=dict(color='red', width=2)
    ))
    fig.add_trace(go.Scatter(
        x=daily['date'], y=daily['place_rate'],
        mode='lines+markers', name='複勝的中率', line=dict(color='blue', width=2)
    ))
    fig.update_layout(
        title="日別 的中率(%)",
        xaxis_title="日付",
        yaxis_title="的中率(%)",
        hovermode='x unified',
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # 累積損益
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=daily['date'], y=daily['cumulative_pnl'],
        mode='lines+markers',
        name='累積純損益', 
        line=dict(color='green', width=3),
        fill='tozeroy',
    ))
    fig2.add_hline(y=0, line_dash="dash", line_color="gray")
    fig2.update_layout(
        title="累積純損益 (円)",
        xaxis_title="日付",
        yaxis_title="累積純損益 (円)",
        height=400,
    )
    st.plotly_chart(fig2, use_container_width=True)
    
    # 累積ROI
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=daily['date'], y=daily['cumulative_roi'],
        mode='lines+markers',
        name='累積ROI',
        line=dict(color='purple', width=3),
    ))
    fig3.add_hline(y=100, line_dash="dash", line_color="green", annotation_text="損益分岐 (100%)")
    fig3.update_layout(
        title="累積回収率 (%)",
        xaxis_title="日付",
        yaxis_title="累積ROI(%)",
        height=400,
    )
    st.plotly_chart(fig3, use_container_width=True)


# ============================================================
# タブ2: グレード別
# ============================================================

with tab2:
    st.subheader("グレード(S/A/B/C)別パフォーマンス")
    
    by_grade = df.groupby('grade').agg(
        races=('race_no', 'count'),
        win=('hit_win', 'sum'),
        place=('hit_place', 'sum'),
        quinella=('hit_quinella', 'sum'),
        trio=('hit_trio_box', 'sum'),
        bet=('race_no', lambda x: len(x) * 100),
        payout=('win_pay', 'sum'),
    ).reset_index()
    by_grade['単勝%'] = (by_grade['win'] / by_grade['races'] * 100).round(1)
    by_grade['複勝%'] = (by_grade['place'] / by_grade['races'] * 100).round(1)
    by_grade['馬連%'] = (by_grade['quinella'] / by_grade['races'] * 100).round(1)
    by_grade['3連複%'] = (by_grade['trio'] / by_grade['races'] * 100).round(1)
    by_grade['ROI'] = (by_grade['payout'] / by_grade['bet'] * 100).round(1)
    by_grade['純損益'] = (by_grade['payout'] - by_grade['bet']).astype(int)
    
    # グレード順
    grade_order = ['S', 'A', 'B', 'C']
    by_grade['__order'] = by_grade['grade'].map({g: i for i, g in enumerate(grade_order)})
    by_grade = by_grade.sort_values('__order').drop(columns=['__order'])
    
    st.dataframe(
        by_grade[['grade', 'races', '単勝%', '複勝%', '馬連%', '3連複%', 'ROI', '純損益']]
        .rename(columns={'grade':'グレード', 'races':'レース数'}),
        use_container_width=True,
        hide_index=True,
    )
    
    # グレード別ROI棒グラフ
    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(
            by_grade, x='grade', y='ROI',
            color='ROI',
            color_continuous_scale='RdYlGn',
            color_continuous_midpoint=100,
            text='ROI',
            title="グレード別 単勝ROI(%)",
            labels={'grade':'グレード'},
        )
        fig.update_traces(texttemplate='%{text:.0f}%', textposition='outside')
        fig.add_hline(y=100, line_dash="dash", line_color="black")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # 的中率比較
        melt = by_grade.melt(
            id_vars='grade',
            value_vars=['単勝%', '複勝%', '馬連%', '3連複%'],
            var_name='券種', value_name='的中率',
        )
        fig = px.bar(
            melt, x='grade', y='的中率',
            color='券種', barmode='group',
            title="グレード別 券種別的中率",
            labels={'grade':'グレード', '的中率':'的中率(%)'},
        )
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# タブ3: 戦略別 ROI
# ============================================================

with tab3:
    st.subheader("戦略別ROI ベンチマーク")
    
    # 各戦略でROI計算
    strategies = []
    
    # 単勝
    strategies.append({
        '戦略': 'AI ◎ 単勝 (全レース)',
        '対象': len(df),
        '的中': int(df['hit_win'].sum()),
        '投資': len(df) * 100,
        '回収': int(df['win_pay'].sum()),
    })
    
    # S級のみ単勝
    s_df = df[df['grade'] == 'S']
    if len(s_df) > 0:
        strategies.append({
            '戦略': 'AI ◎ 単勝 (S級のみ)',
            '対象': len(s_df),
            '的中': int(s_df['hit_win'].sum()),
            '投資': len(s_df) * 100,
            '回収': int(s_df['win_pay'].sum()),
        })
    
    # 高オッズフィルタ (期待値≥1.0)
    df['ev'] = df['ai_top1_conf'] * df['ai_top1_odds']
    ev_df = df[df['ev'] >= 1.0]
    if len(ev_df) > 0:
        strategies.append({
            '戦略': 'AI ◎ 単勝 (期待値≥1.0)',
            '対象': len(ev_df),
            '的中': int(ev_df['hit_win'].sum()),
            '投資': len(ev_df) * 100,
            '回収': int(ev_df['win_pay'].sum()),
        })
    
    # 重賞限定
    g_df = df[df['class_code'].isin(['Ｇ１','Ｇ２','Ｇ³','G1','G2','G3'])]
    if len(g_df) > 0:
        strategies.append({
            '戦略': 'AI ◎ 単勝 (重賞のみ)',
            '対象': len(g_df),
            '的中': int(g_df['hit_win'].sum()),
            '投資': len(g_df) * 100,
            '回収': int(g_df['win_pay'].sum()),
        })
    
    # ROI計算
    sdf = pd.DataFrame(strategies)
    sdf['ROI%'] = (sdf['回収'] / sdf['投資'] * 100).round(1)
    sdf['的中率%'] = (sdf['的中'] / sdf['対象'] * 100).round(1)
    sdf['純損益'] = (sdf['回収'] - sdf['投資']).astype(int)
    
    sdf = sdf.sort_values('ROI%', ascending=False)
    
    st.dataframe(
        sdf[['戦略', '対象', '的中', '的中率%', '投資', '回収', 'ROI%', '純損益']],
        use_container_width=True,
        hide_index=True,
    )
    
    # ROI棒グラフ
    fig = px.bar(
        sdf, x='戦略', y='ROI%',
        color='ROI%',
        color_continuous_scale='RdYlGn',
        color_continuous_midpoint=100,
        text='ROI%',
        title="戦略別 単勝ROI(%) 比較",
    )
    fig.update_traces(texttemplate='%{text:.0f}%', textposition='outside')
    fig.add_hline(y=100, line_dash="dash", line_color="black", annotation_text="損益分岐 (100%)")
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# タブ4: 詳細記録 (大きな1日分)
# ============================================================

with tab4:
    st.subheader("日別詳細")
    
    sel_date = st.selectbox(
        "表示する日",
        options=sorted(df['date'].dt.strftime('%Y-%m-%d').unique(), reverse=True),
    )
    
    day_df = df[df['date'].dt.strftime('%Y-%m-%d') == sel_date].copy()
    
    if not day_df.empty:
        st.markdown(f"### {sel_date} ({len(day_df)}レース)")
        
        # サマリ
        wn = day_df['hit_win'].sum()
        pn = day_df['hit_place'].sum()
        qn = day_df['hit_quinella'].sum()
        tn = day_df['hit_trio_box'].sum()
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("単勝", f"{wn}/{len(day_df)}", f"{wn/len(day_df)*100:.0f}%")
        c2.metric("複勝", f"{pn}/{len(day_df)}", f"{pn/len(day_df)*100:.0f}%")
        c3.metric("馬連", f"{qn}/{len(day_df)}", f"{qn/len(day_df)*100:.0f}%")
        c4.metric("3連複", f"{tn}/{len(day_df)}", f"{tn/len(day_df)*100:.0f}%")
        
        # レース別詳細
        display = day_df[[
            'place', 'race_no', 'race_name', 'grade',
            'ai_top1_no', 'ai_top1_horse', 'ai_top1_jockey', 'ai_top1_conf',
            'win_no', 'win_name', 'win_odds', 'win_pop',
            'hit_win', 'hit_place', 'overlap_top3',
        ]].copy()
        display['ai_top1_conf'] = (display['ai_top1_conf'] * 100).round(0)
        display['判定'] = display.apply(
            lambda r: ('★単勝' if r['hit_win'] else '') + 
                      (' ★複勝' if r['hit_place'] and not r['hit_win'] else ''),
            axis=1
        )
        display = display.rename(columns={
            'place':'場所', 'race_no':'R', 'race_name':'レース名', 'grade':'G',
            'ai_top1_no':'AI馬番', 'ai_top1_horse':'AI馬名', 
            'ai_top1_jockey':'AI騎手', 'ai_top1_conf':'AI%',
            'win_no':'1着馬番', 'win_name':'1着馬', 'win_odds':'単勝',
            'win_pop':'人気', 'overlap_top3':'AI上位3頭中',
        })
        display = display.drop(columns=['hit_win', 'hit_place'])
        
        st.dataframe(display, use_container_width=True, hide_index=True)


# ============================================================
# タブ5: 全レース一覧
# ============================================================

with tab5:
    st.subheader("📋 全レース一覧")
    
    # フィルタ
    col1, col2 = st.columns(2)
    only_hit = col1.checkbox("単勝的中のみ表示")
    only_top1_top3 = col2.checkbox("AI◎が3着内のみ表示")
    
    display_df = df.copy()
    if only_hit:
        display_df = display_df[display_df['hit_win']]
    if only_top1_top3:
        display_df = display_df[display_df['hit_place']]
    
    show_cols = ['date', 'place', 'race_no', 'race_name', 'grade',
                  'ai_top1_no', 'ai_top1_horse', 'ai_top1_conf',
                  'win_no', 'win_name', 'win_odds',
                  'hit_win', 'hit_place', 'overlap_top3']
    
    display_df = display_df[show_cols].copy()
    display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
    display_df['ai_top1_conf'] = (display_df['ai_top1_conf'] * 100).round(0).astype(int).astype(str) + '%'
    display_df['hit_win'] = display_df['hit_win'].map({True:'★', False:''})
    display_df['hit_place'] = display_df['hit_place'].map({True:'○', False:''})
    
    display_df = display_df.rename(columns={
        'date':'日付', 'place':'場所', 'race_no':'R',
        'race_name':'レース名', 'grade':'G',
        'ai_top1_no':'AI馬番', 'ai_top1_horse':'AI馬名',
        'ai_top1_conf':'AI%',
        'win_no':'1着馬番', 'win_name':'1着馬', 'win_odds':'オッズ',
        'hit_win':'単勝', 'hit_place':'複勝',
        'overlap_top3':'AI top3 of 3',
    })
    
    st.dataframe(display_df, use_container_width=True, hide_index=True, height=500)
    st.caption(f"{len(display_df)} レース表示中")


# ============================================================
# フッタ
# ============================================================

st.divider()
st.caption(f"📂 累積ログ: `{LOG_FILE}`")
st.caption(f"📅 記録日数: {df['date'].nunique()} 日 / 総レース数: {len(df)}")
