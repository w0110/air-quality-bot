import requests
import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, LocationMessage, TextSendMessage
from geopy.distance import geodesic

def fetch_all_data(base_url):
    data = []
    while base_url:
        response = requests.get(base_url, verify=False)
        if response.status_code == 200:
            json_response = response.json()
            data.extend(json_response['value'])
            base_url = json_response.get('@iot.nextLink')
        else:
            print("Failed to retrieve data from the API")
            base_url = None
    return data

def get_air_quality_description(aqi):
    if aqi <= 50:
        return "良好", "green"
    elif aqi <= 100:
        return "普通", "beige"
    elif aqi <= 150:
        return "對敏感族群不健康", "orange"
    elif aqi <= 200:
        return "對所有族群不健康", "red"
    elif aqi <= 300:
        return "非常不健康", "purple"
    elif aqi <= 500:
        return "危害", "maroon"
    else:
        return "無效數據", "gray"

def get_nearest_station(user_coordinates, stations_info):
    nearest_station = None
    min_distance = float('inf')

    for station_info in stations_info:
        station_name = station_info['name']
        station_coordinates = station_info['coordinates']
        distance = geodesic(user_coordinates, station_coordinates).kilometers
        if distance < min_distance:
            min_distance = distance
            nearest_station = station_info
    
    return nearest_station

# 發送請求並獲取測站資料，忽略SSL憑證的驗證
station_url = "https://sta.ci.taiwan.gov.tw/STA_AirQuality_v2/v1.0/Things?$expand=Locations&$select=name,properties&$count=true&$filter=substringof(%27%E7%A9%BA%E6%B0%A3%E5%93%81%E8%B3%AA%E6%B8%AC%E7%AB%99%27,name)"
stations_response = requests.get(station_url, verify=False)

if stations_response.status_code == 200:
    stations_data = stations_response.json()
    stations_info = []

    for station in stations_data['value']:
        station_name = station['name']
        station_longitude = station['Locations'][0]['location']['coordinates'][0]
        station_latitude = station['Locations'][0]['location']['coordinates'][1]
        stations_info.append({
            'name': station_name,
            'coordinates': (station_latitude, station_longitude)
        })
else:
    print("Failed to retrieve station data from the API")

# 發送請求並獲取監測資料，忽略SSL憑證的驗證
url2 = "https://sta.ci.taiwan.gov.tw/STA_AirQuality_v2/v1.0/Datastreams?$expand=Thing,Observations($orderby=phenomenonTime%20desc;$top=1)&$filter=%20substringof(%27%E7%A9%BA%E6%B0%A3%E5%93%81%E8%B3%AA%E6%B8%AC%E7%AB%99%27,Thing/name)&$count=true"
datastreams_data = fetch_all_data(url2)
response = requests.get(url2, verify=False)

# 檢查請求是否成功
if response.status_code == 200:
    data2 = response.json()

    # 初始化監測站的 AQI 和時間戳記列表
    stations_aqi = {info['name']: None for info in stations_info}
    stations_timestamp = {info['name']: None for info in stations_info}

    for item in datastreams_data:
        if item['description'] == '空氣品質指標' and item['name'] == 'AQI':
            station_name = item['Thing']['name']
            aqi = item['Observations'][0]['result']
            timestamp = item['Observations'][0]['phenomenonTime']
            stations_aqi[station_name] = aqi
            stations_timestamp[station_name] = timestamp
else:
    print("Failed to retrieve sensor data from the API")

# 定義 Flask 應用程式
app = Flask(__name__)

# 使用環境變數設定 Line Bot API 和 Webhook Handler
line_bot_api = LineBotApi(channel_access_token=os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(channel_secret=os.getenv('LINE_CHANNEL_SECRET'))

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
    user_coordinates = (event.message.latitude, event.message.longitude)
    print(user_coordinates)
    nearest_station = get_nearest_station(user_coordinates, stations_info)
    print(nearest_station)

    if nearest_station:
        station_name = nearest_station['name']
        aqi = stations_aqi.get(station_name)
        timestamp = stations_timestamp.get(station_name)

        if aqi is not None:
            description, color = get_air_quality_description(aqi)
            reply_text = f"最近的監測站：{station_name}\nAQI：{aqi}\n空氣品質：{description}\n更新時間：{timestamp}"
        else:
            reply_text = f"最近的監測站：{station_name}\n沒有可用的 AQI 資料"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="找不到附近的監測站")
        )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
