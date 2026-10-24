import json
import os
import urllib.request
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import random

# --- 0. เตรียมข้อมูลแผนที่ ---
def setup_geojson():
    geojson_file = "thailand_provinces.geojson"
    if not os.path.exists(geojson_file):
        st.info("กำลังดาวน์โหลดแผนที่ประเทศไทย...")
        url = "https://raw.githubusercontent.com/apisit/thailand.json/master/thailand.json"
        try:
            urllib.request.urlretrieve(url, geojson_file)
            st.success("ดาวน์โหลดแผนที่สำเร็จ")
        except Exception as e:
            st.error(f"ดาวน์โหลดแผนที่ไม่สำเร็จ: {e}")
            st.stop()
    with open(geojson_file, "r", encoding="utf-8") as f:
        return json.load(f)

geojson = setup_geojson()

# --- 1. หาจุดกึ่งกลางจังหวัด (แบบไม่ใช้ shapely) ---
@st.cache_data
def get_centroids(geojson_data):
    centroids = {}
    for feat in geojson_data["features"]:
        name = feat["properties"].get("name", "")
        if not name: continue
        
        # ดึงพิกัดทั้งหมดของจังหวัดนั้นมาหาค่าเฉลี่ย
        coords = []
        def extract_coords(geom):
            if geom['type'] == 'Polygon':
                coords.extend(geom['coordinates'][0])
            elif geom['type'] == 'MultiPolygon':
                for poly in geom['coordinates']:
                    coords.extend(poly[0])
        
        extract_coords(feat["geometry"])
        
        if coords:
            avg_lat = sum([c[1] for c in coords]) / len(coords)
            avg_lon = sum([c[0] for c in coords]) / len(coords)
            centroids[name] = (avg_lat, avg_lon)
            
    return centroids

centroids = get_centroids(geojson)

# --- 2. Mapping ชื่อจังหวัด TH -> EN ---
TH_TO_EN = {
    "กรุงเทพ": "Bangkok", "กรุงเทพมหานคร": "Bangkok", "กระบี่": "Krabi", "กาญจนบุรี": "Kanchanaburi", "กาฬสินธุ์": "Kalasin", "กำแพงเพชร": "Kamphaeng Phet",
    "ขอนแก่น": "Khon Kaen", "จันทบุรี": "Chanthaburi", "ฉะเชิงเทรา": "Chachoengsao", "ชลบุรี": "Chon Buri", "ชัยนาท": "Chai Nat", "ชัยภูมิ": "Chaiyaphum",
    "ชุมพร": "Chumphon", "เชียงราย": "Chiang Rai", "เชียงใหม่": "Chiang Mai", "ตรัง": "Trang", "ตราด": "Trat", "ตาก": "Tak", "นครนายก": "Nakhon Nayok",
    "นครปฐม": "Nakhon Pathom", "นครพนม": "Nakhon Phanom", "นครราชสีมา": "Nakhon Ratchasima", "นครศรีธรรมราช": "Nakhon Si Thammarat", "นครสวรรค์": "Nakhon Sawan",
    "นนทบุรี": "Nonthaburi", "นราธิวาส": "Narathiwat", "น่าน": "Nan", "บึงกาฬ": "Bueng Kan", "บุรีรัมย์": "Buriram", "ปทุมธานี": "Pathum Thani",
    "ประจวบคีรีขันธ์": "Prachuap Khiri Khan", "ปราจีนบุรี": "Prachinburi", "ปัตตานี": "Pattani", "พระนครศรีอยุธยา": "Ayutthaya", "พะเยา": "Phayao",
    "พังงา": "Phang Nga", "พัทลุง": "Phatthalung", "พิจิตร": "Phichit", "พิษณุโลก": "Phitsanulok", "เพชรบุรี": "Phetchaburi", "เพชรบูรณ์": "Phetchabun",
    "แพร่": "Phrae", "ภูเก็ต": "Phuket", "มหาสารคาม": "Maha Sarakham", "มุกดาหาร": "Mukdahan", "แม่ฮ่องสอน": "Mae Hong Son", "ยะลา": "Yala",
    "ยโสธร": "Yasothon", "ร้อยเอ็ด": "Roi Et", "ระนอง": "Ranong", "ระยอง": "Rayong", "ราชบุรี": "Ratchaburi", "ลพบุรี": "Lopburi",
    "ลำปาง": "Lampang", "ลำพูน": "Lamphun", "เลย": "Loei", "ศรีสะเกษ": "Sisaket", "สกลนคร": "Sakon Nakhon", "สงขลา": "Songkhla",
    "สตูล": "Satun", "สมุทรปราการ": "Samut Prakan", "สมุทรสงคราม": "Samut Songkhram", "สมุทรสาคร": "Samut Sakhon", "สระแก้ว": "Sa Kaeo", "สระบุรี": "Saraburi",
    "สิงห์บุรี": "Sing Buri", "สุโขทัย": "Sukhothai", "สุพรรณบุรี": "Suphan Buri", "สุราษฎร์ธานี": "Surat Thani", "สุรินทร์": "Surin", "หนองคาย": "Nong Khai",
    "หนองบัวลำภู": "Nong Bua Lamphu", "อ่างทอง": "Ang Thong", "อำนาจเจริญ": "Amnat Charoen", "อุดรธานี": "Udon Thani", "อุตรดิตถ์": "Uttaradit", "อุทัยธานี": "Uthai Thani",
    "อุบลราชธานี": "Ubon Ratchathani", "เบตง": "Betong", "หัวหิน": "Hua Hin", "หาดใหญ่": "Hat Yai", "เกาะสมุย": "Koh Samui"
}

# --- 3. สร้างข้อมูล GPP ตัวอย่าง ---
csv_file = "gpp_2567.csv"
if not os.path.exists(csv_file):
    provinces_en = list(centroids.keys())
    data = {
        "province_name": provinces_en,
        "gpp_per_capita": [random.randint(60000, 900000) for _ in provinces_en],
        "gpp_rank": list(range(1, len(provinces_en) + 1))
    }
    pd.DataFrame(data).to_csv(csv_file, index=False, encoding="utf-8")

df_gpp = pd.read_csv(csv_file, encoding="utf-8")

# --- 4. โหลดข้อมูลเส้นทางรถ ---
@st.cache_data
def load_bus_routes():
    try:
        # พยายามโหลดจาก Hugging Face
        from datasets import load_dataset
        ds = load_dataset("pythainlp/Thailand-Transport-Bus", split="train")
        df = ds.to_pandas()[["origin", "destination"]].dropna()
        return df
    except Exception as e:
        # ถ้าโหลดไม่ได้ (หรือยังไม่ได้ลง datasets) ให้ใช้ข้อมูลจำลอง
        st.warning("ไม่สามารถโหลดข้อมูลรถเมล์จริงได้ (ใช้ข้อมูลจำลองแทน) หากต้องการใช้ข้อมูลจริงให้พิมพ์ `pip install datasets` ใน Terminal")
        return pd.DataFrame({
            "origin": ["ขอนแก่น", "นครราชสีมา", "กรุงเทพ", "กรุงเทพ", "อุดรธานี", "อุบลราชธานี", "ภูเก็ต", "หาดใหญ่", "เชียงใหม่", "เชียงราย"],
            "destination": ["อุดรธานี", "ขอนแก่น", "ภูเก็ต", "เชียงใหม่", "หนองคาย", "นครราชสีมา", "พังงา", "สงขลา", "ลำปาง", "พะเยา"]
        })

df_routes = load_bus_routes()

# --- 5. แปลงชื่อจังหวัดเป็นพิกัด ---
def get_coord(th_name):
    if pd.isna(th_name): return None
    en_name = TH_TO_EN.get(str(th_name).strip())
    return centroids.get(en_name) if en_name else None

route_coords = []
for _, row in df_routes.iterrows():
    o, d = get_coord(row["origin"]), get_coord(row["destination"])
    if o and d:
        route_coords.append((o, d))

# --- 6. สร้างแผนที่ ---
st.set_page_config(page_title="GPP & Bus Routes", layout="wide")
st.title("🇹🇭 GPP per capita + เส้นทางรถโดยสารระหว่างจังหวัด")

fig = go.Figure()

# ชั้นที่ 1: สีจังหวัด (GPP)
fig.add_trace(go.Choropleth(
    geojson=geojson,
    locations=df_gpp["province_name"],
    z=df_gpp["gpp_per_capita"],
    featureidkey="properties.name",
    colorscale="RdYlGn",
    zmin=df_gpp["gpp_per_capita"].min(),
    zmax=df_gpp["gpp_per_capita"].max(),
    marker_line_width=0.5,
    colorbar_title="GPP<br>บาท/คน/ปี"
))

# ชั้นที่ 2: เส้นทางรถ
for (lat1, lon1), (lat2, lon2) in route_coords:
    fig.add_trace(go.Scattergeo(
        lon=[lon1, lon2], lat=[lat1, lat2],
        mode="lines",
        line=dict(width=1.5, color="rgba(50,50,50,0.6)"),
        hoverinfo="skip",
        showlegend=False
    ))

# ชั้นที่ 3: จุดเชื่อมต่อ
unique_points = {}
for (lat1, lon1), (lat2, lon2) in route_coords:
    unique_points[(lat1, lon1)] = True
    unique_points[(lat2, lon2)] = True

fig.add_trace(go.Scattergeo(
    lon=[p[1] for p in unique_points],
    lat=[p[0] for p in unique_points],
    mode="markers",
    marker=dict(size=6, color="black"),
    hoverinfo="skip",
    showlegend=False
))

fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(height=700, margin={"r":0,"t":30,"l":0,"b":0})
st.plotly_chart(fig, use_container_width=True)

st.caption(f"แสดง {len(route_coords)} เส้นทาง")