import json
from typing import List

import streamlit as st
from google import genai
from google.genai import types

# ========== UI 基本設定 ==========
st.set_page_config(page_title="X×Y 組み合わせ生成（Gemini）", layout="wide")
st.title("X×Y 組み合わせ生成（Gemini）")
st.caption("• Gemini APIを使用します。APIキーはご自身のものをご利用ください。")
st.markdown("---")

# ========== サイドバー ==========
with st.sidebar:
    st.header("設定")
    api_key = st.text_input("Gemini API Key", type="password", help="Google AI Studioで取得したAPIキーを入力")
    st.caption("※ `.streamlit/secrets.toml` に `GEMINI_API_KEY` を保存している場合は空欄でもOK")
    if not api_key:
        api_key = st.secrets.get("GEMINI_API_KEY", "")

    # モード切り替え
    mode = st.radio(
        "X_list / Y_list の指定方法",
        ["Geminiで自動生成する", "手入力する（改行区切り）"],
        index=0
    )

    # モデル名（将来の変更に備えて外出し）
    model_name = st.text_input("Model", value="gemini-2.5-flash")
    st.caption("※ 生成スピード重視の既定値です。必要に応じて変更してください。")

# ========== Gemini クライアント ==========
def make_client(_api_key: str) -> genai.Client:
    if not _api_key:
        st.stop()
    return genai.Client(api_key=_api_key)

# grounding ツール（Google Search）を有効に
grounding_tool = types.Tool(google_search=types.GoogleSearch())
gen_config = types.GenerateContentConfig(tools=[grounding_tool])

def gen_response(client: genai.Client, question: str) -> str:
    resp = client.models.generate_content(
        model=model_name,
        contents=question,
        config=gen_config,
    )
    return (resp.text or "").strip()

def list_gen(client: genai.Client, prompt: str) -> List[str]:
    """GeminiにJSONのリストとして返してもらう"""
    resp = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": list,
        },
    )
    # .parsed が使える実装に合わせる
    data = getattr(resp, "parsed", None)
    if isinstance(data, list):
        return [str(x).strip() for x in data if str(x).strip()]
    # フォールバック（JSON文字列で返った場合）
    try:
        parsed = json.loads(resp.text)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except Exception:
        pass
    # 最終手段：改行や箇条書きを分解
    text = (resp.text or "").strip()
    lines = [ln.strip("-• \t") for ln in text.splitlines() if ln.strip()]
    return lines

# ========== 入力UI ==========
col1, col2 = st.columns(2)

with col1:
    st.subheader("Xの設定")
    if mode == "Geminiで自動生成する":
        x_topics = st.text_area(
            "X_TOPICS プロンプト",
            value="業種を3個あげて。回答はJSONの配列（日本語）で。",
            height=110
        )
    else:
        x_manual = st.text_area(
            "X_list（改行区切り）",
            value="製造業\n小売業\n金融業",
            height=160
        )

with col2:
    st.subheader("Yの設定")
    if mode == "Geminiで自動生成する":
        y_topics = st.text_area(
            "Y_TOPICS プロンプト",
            value="生成AIの導入を評価するポイントを3つあげて。回答はJSONの配列（日本語）で。",
            height=110
        )
    else:
        y_manual = st.text_area(
            "Y_list（改行区切り）",
            value="コスト削減\n品質向上\n業務効率化",
            height=160
        )

st.subheader("質問テンプレート")
question_template = st.text_area(
    "テンプレート（X と Y を置換）",
    value="Xにおいて、生成AIの導入に関してYで成功した事例を検索して探して、文章にしてください。",
    height=90,
    help="X と Y の文字列がそのまま置換されます。"
)

run = st.button("▶ 生成を開始", type="primary")

# ========== 実行 ==========
if run:
    if not api_key:
        st.error("Gemini API Key を入力してください。")
        st.stop()

    client = make_client(api_key)

    if mode == "Geminiで自動生成する":
        with st.spinner("X_list を生成中..."):
            X_list = list_gen(client, x_topics)
        with st.spinner("Y_list を生成中..."):
            Y_list = list_gen(client, y_topics)
    else:
        X_list = [ln.strip() for ln in x_manual.splitlines() if ln.strip()]
        Y_list = [ln.strip() for ln in y_manual.splitlines() if ln.strip()]

    if not X_list or not Y_list:
        st.warning("X_list または Y_list が空です。設定を確認してください。")
        st.stop()

    st.success(f"X: {len(X_list)}件 / Y: {len(Y_list)}件 で実行します。")
    st.markdown("---")

    # 進捗表示
    total = len(X_list) * len(Y_list)
    progress = st.progress(0)
    done = 0

    # レンダリング領域
    results_container = st.container()

    for xi, x_word in enumerate(X_list):
        with results_container:
            st.markdown(f"### 🧩 X = {x_word}")

        for yi, y_word in enumerate(Y_list):
            query = question_template.replace("X", x_word).replace("Y", y_word)

            with st.spinner(f"生成中: X={x_word} × Y={y_word}"):
                answer = gen_response(client, query)

            # 各結果ブロックを順次表示
            with results_container:
                st.markdown(f"#### Y = {y_word}")

                # 結果テキスト（見やすいように）
                st.write(answer if answer else "（空の応答）")

                # クリップボードコピー（JS）
                # content は JSON エスケープして埋め込む
                payload = json.dumps(answer or "", ensure_ascii=False)
                uid = f"copy_{xi}_{yi}"

                st.components.v1.html(
                    f"""
                    <div style="margin: 4px 0 18px 0;">
                      <button id="{uid}_btn">コピー</button>
                      <span id="{uid}_msg" style="margin-left:8px;font-size:12px;color:gray;"></span>
                    </div>
                    <script>
                      const btn_{uid} = document.getElementById("{uid}_btn");
                      const msg_{uid} = document.getElementById("{uid}_msg");
                      btn_{uid}.addEventListener("click", async () => {{
                        try {{
                          await navigator.clipboard.writeText({payload});
                          msg_{uid}.textContent = "コピーしました";
                          setTimeout(() => msg_{uid}.textContent = "", 1500);
                        }} catch (e) {{
                          msg_{uid}.textContent = "コピーに失敗しました";
                          setTimeout(() => msg_{uid}.textContent = "", 1500);
                        }}
                      }});
                    </script>
                    """,
                    height=50,
                )

            done += 1
            progress.progress(int(done / total * 100))

    st.success("すべての組み合わせの生成が完了しました ✅")
    st.balloons()

# ========== 注意事項 ==========
with st.expander("免責・注意（重要）", expanded=False):
    st.markdown(
        """
- これは記事作成の**補助ツール**です。生成結果の正確性・適法性（著作権・商標・機密・誹謗中傷・個人情報など）は**利用者の責任**でご確認ください。
- GoogleやGitHub、Streamlit Cloudなど**外部サービスの停止**や**API制限**により本アプリは正常に動作しない場合があります。
- APIキーは**ご自身で取得し**、自己責任でご利用ください。キーの保管・流出対策は各自で実施してください。
"""
    )
