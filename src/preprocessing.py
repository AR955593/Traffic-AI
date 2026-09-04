import pandas as pd
import numpy as np

class DataPreprocessor:
    """
    Handles cleaning, missing GPS interpolation, normalization, and encoding.
    """
    def __init__(self):
        self.road_type_map = {"Highway": 0, "Arterial": 1, "City_Street": 2, "Residential": 3}
        self.weather_map = {"Clear": 0, "Cloudy": 1, "Fog": 2, "Rain": 3, "Heavy Rain": 4, "Snow": 5}
        self.congestion_level_map = {"Low": 0, "Moderate": 1, "Heavy": 2, "Severe": 3}
        self.rev_congestion_level_map = {v: k for k, v in self.congestion_level_map.items()}

    def clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Cleans raw dataframe:
        - Parses timestamp
        - Interpolates missing GPS lat/lon coordinates
        - Fills missing numerical weather values with medians
        """
        df = df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)

        # Handle missing GPS points using linear interpolation & ffill/bfill fallback
        df['latitude'] = df['latitude'].interpolate(method='linear').bfill().ffill()
        df['longitude'] = df['longitude'].interpolate(method='linear').bfill().ffill()

        # Handle any missing numeric weather variables if present
        for col in ['temperature_c', 'precipitation_mm', 'humidity_percent', 'wind_speed_kmh', 'visibility_km']:
            if col in df.columns:
                df[col] = df[col].fillna(df[col].median())

        return df

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Encodes categorical variables into integer representations.
        """
        df = self.clean_data(df)
        
        if 'road_type' in df.columns:
            df['road_type_encoded'] = df['road_type'].map(self.road_type_map).fillna(2).astype(int)
        
        if 'weather_condition' in df.columns:
            df['weather_condition_encoded'] = df['weather_condition'].map(self.weather_map).fillna(0).astype(int)

        if 'congestion_level' in df.columns:
            df['congestion_level_encoded'] = df['congestion_level'].map(self.congestion_level_map).fillna(0).astype(int)

        return df

if __name__ == "__main__":
    import os
    raw_path = os.path.join(os.path.dirname(__file__), "..", "data", "raw_traffic_weather.csv")
    if os.path.exists(raw_path):
        df_raw = pd.read_csv(raw_path)
        processor = DataPreprocessor()
        df_clean = processor.transform(df_raw)
        print("Data preprocessed successfully! Sample:")
        print(df_clean[['timestamp', 'latitude', 'longitude', 'road_type_encoded', 'weather_condition_encoded']].head())
