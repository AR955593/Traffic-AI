import numpy as np
import pandas as pd
import os
from datetime import datetime, timedelta

def generate_traffic_weather_data(num_records=5000, seed=42):
    """
    Generates a realistic urban traffic and weather dataset for ML training.
    """
    np.random.seed(seed)
    
    # Base location around a representative metropolitan city center
    base_lat, base_lon = 40.7128, -74.0060
    
    start_date = datetime(2026, 1, 1)
    
    timestamps = [start_date + timedelta(minutes=15 * i) for i in range(num_records)]
    
    road_types = ["Highway", "Arterial", "City_Street", "Residential"]
    weather_conditions = ["Clear", "Cloudy", "Rain", "Heavy Rain", "Fog", "Snow"]
    
    data = []
    
    for i, ts in enumerate(timestamps):
        hour = ts.hour
        day_of_week = ts.weekday()
        is_weekend = 1 if day_of_week >= 5 else 0
        
        # Spatial randomness around major arterial corridors
        corridor = np.random.choice([0, 1, 2, 3])
        lat_offset = (np.sin(i / 100) * 0.05) + np.random.normal(0, 0.008)
        lon_offset = (np.cos(i / 100) * 0.05) + np.random.normal(0, 0.008)
        
        # Simulate missing GPS coordinate occasionally (~2% of data to demonstrate cleaning)
        if np.random.rand() < 0.02:
            lat, lon = np.nan, np.nan
        else:
            lat = base_lat + lat_offset
            lon = base_lon + lon_offset
            
        road = road_types[corridor]
        
        # Base speed by road type (km/h)
        base_speed_map = {"Highway": 90, "Arterial": 60, "City_Street": 40, "Residential": 30}
        max_speed = base_speed_map[road]
        
        # Peak hours: Morning rush (7-9 AM), Evening rush (5-7 PM)
        is_morning_rush = 1 if 7 <= hour <= 9 and not is_weekend else 0
        is_evening_rush = 1 if 17 <= hour <= 19 and not is_weekend else 0
        is_rush_hour = 1 if (is_morning_rush or is_evening_rush) else 0
        
        # Weather simulation
        weather_prob = [0.45, 0.25, 0.15, 0.05, 0.05, 0.05]
        weather = np.random.choice(weather_conditions, p=weather_prob)
        
        # Temp in Celsius
        temp = round(float(np.random.normal(20 - (5 if weather in ["Rain", "Heavy Rain", "Snow"] else 0), 5)), 1)
        
        # Precipitation in mm/h
        if weather == "Heavy Rain":
            precip = round(float(np.random.uniform(8.0, 25.0)), 1)
            visibility_km = round(float(np.random.uniform(1.0, 4.0)), 1)
        elif weather == "Rain":
            precip = round(float(np.random.uniform(1.0, 7.9)), 1)
            visibility_km = round(float(np.random.uniform(4.0, 8.0)), 1)
        elif weather == "Snow":
            precip = round(float(np.random.uniform(2.0, 12.0)), 1)
            visibility_km = round(float(np.random.uniform(0.5, 3.0)), 1)
        elif weather == "Fog":
            precip = 0.0
            visibility_km = round(float(np.random.uniform(0.2, 1.5)), 1)
        else:
            precip = 0.0
            visibility_km = round(float(np.random.uniform(8.0, 15.0)), 1)
            
        humidity = int(np.clip(np.random.normal(60 + precip * 2, 15), 20, 100))
        wind_speed = round(float(np.random.uniform(2.0, 35.0)), 1)
        
        # Calculate speed reduction factor based on rush hour, weather, and road type
        rush_factor = 0.45 if is_rush_hour else 0.90
        if is_weekend and 12 <= hour <= 18:
            rush_factor = 0.75
            
        weather_factor = 1.0
        if weather == "Rain":
            weather_factor = 0.82
        elif weather == "Heavy Rain":
            weather_factor = 0.60
        elif weather == "Fog":
            weather_factor = 0.70
        elif weather == "Snow":
            weather_factor = 0.50
            
        noise = np.random.uniform(0.85, 1.15)
        
        actual_speed = round(float(np.clip(max_speed * rush_factor * weather_factor * noise, 5.0, max_speed)), 1)
        
        # Congestion index from 0.0 (free flow) to 1.0 (gridlock)
        congestion_index = round(float(np.clip(1.0 - (actual_speed / max_speed), 0.0, 1.0)), 3)
        
        # Congestion Label (0: Low, 1: Moderate, 2: Heavy, 3: Severe)
        if congestion_index < 0.25:
            congestion_level = "Low"
        elif congestion_index < 0.55:
            congestion_level = "Moderate"
        elif congestion_index < 0.80:
            congestion_level = "Heavy"
        else:
            congestion_level = "Severe"
            
        data.append({
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "latitude": lat,
            "longitude": lon,
            "road_type": road,
            "max_speed_kmh": max_speed,
            "current_speed_kmh": actual_speed,
            "congestion_index": congestion_index,
            "congestion_level": congestion_level,
            "temperature_c": temp,
            "humidity_percent": humidity,
            "wind_speed_kmh": wind_speed,
            "precipitation_mm": precip,
            "visibility_km": visibility_km,
            "weather_condition": weather,
            "is_weekend": is_weekend,
            "is_rush_hour": is_rush_hour
        })
        
    df = pd.DataFrame(data)
    
    os.makedirs(os.path.dirname(__file__) if os.path.dirname(__file__) else ".", exist_ok=True)
    output_path = os.path.join(os.path.dirname(__file__), "raw_traffic_weather.csv")
    df.to_csv(output_path, index=False)
    print(f"Successfully generated dataset with {len(df)} records at: {output_path}")
    return output_path

if __name__ == "__main__":
    generate_traffic_weather_data()
