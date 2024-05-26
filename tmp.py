from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, LocationMessage

app = Flask(__name__)

# Line Bot API 和 Webhook Handler 設定
line_bot_api = LineBotApi('你的 Channel Access Token')
handler = WebhookHandler('你的 Channel Secret')

@app.route("/callback", methods=['POST'])
def callback():
    # 獲取 Line 傳送的請求的標頭和正文
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")

    # 驗證請求
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Check your channel access token/channel secret.")
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    # 回傳使用者傳送的文字訊息
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=event.message.text))

@handler.add(MessageEvent, message=LocationMessage)
def handle_location_message(event):
    # 獲取使用者位置訊息
    latitude = event.message.latitude
    longitude = event.message.longitude
    address = event.message.address

    # 回應使用者位置訊息
    reply_text = f"你的位置資訊：\n地址：{address}\n緯度：{latitude}\n經度：{longitude}"
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run(debug=True)
