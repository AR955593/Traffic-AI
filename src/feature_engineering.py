import pandas as pd
import numpy as np

class FeatureEngineer:
    """
    Creates temporal, weather impact, road capacity, and time-series lag features.
    """
    
    @staticmethod
    def calculate_weather_impact_index(precip_mm, visibility_km, weather_encoded):
        """
        Calculates a 0.0 to 1.0 weather impact index score.
        """
        # Precipitation contribution (0 to 0.5)
        precip_score = min(precip_mm / 25.0, 0.5)
        
        # Visibility contribution (0 to 0.3)
        vis_score = max(0.0, (10.0 - min(visibility_km, 10.0)) / 10.0) * 0.3
        
        # Weather type bonus (0 to 0.2)
        type_score = min(weather_encoded / 5.0, 1.0) * 0.2
        
        return round(float(np.clip(precip_score + vis_score + type_score, 0.0, 1.0)), 3)

    def extract_features(self, df: pd.DataFrame, include_lags: bool = True) -> pd.DataFrame:
        """
        Applies feature extraction pipeline on preprocessed dataframe.
        """
        df = df.copy()
        
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
        # 1. Temporal cyclic features
        hour = df['timestamp'].dt.hour
        dayofweek = df['timestamp'].dt.dayofweek
        
        df['hour'] = hour
        df['dayofweek'] = dayofweek
        df['is_weekend'] = (dayofweek >= 5).astype(int)
        
        # Sin/Cos cyclicity for hour (24h period) and day (7d period)
        df['hour_sin'] = np.sin(2 * np.pi * hour / 24.0)
        df['hour_cos'] = np.cos(2 * np.pi * hour / 24.0)
        df['day_sin'] = np.sin(2 * np.pi * dayofweek / 7.0)
        df['day_cos'] = np.cos(2 * np.pi * dayofweek / 7.0)
        
        # Rush hour indicator
        df['is_rush_hour'] = (((hour >= 7) & (hour <= 9)) | ((hour >= 17) & (hour <= 19))) & (df['is_weekend'] == 0)
        df['is_rush_hour'] = df['is_rush_hour'].astype(int)
        
        # 2. Weather Impact Index
        if 'weather_impact_index' not in df.columns:
            df['weather_impact_index'] = df.apply(
                lambda row: self.calculate_weather_impact_index(
                    row.get('precipitation_mm', 0),
                    row.get('visibility_km', 10),
                    row.get('weather_condition_encoded', 0)
                ), axis=1
            )
            
        # 3. Time Series Lags (for sequential temporal dependencies)
        if include_lags and 'current_speed_kmh' in df.columns:
            df['speed_lag_1'] = df['current_speed_kmh'].shift(1).bfill()
            df['speed_lag_2'] = df['current_speed_kmh'].shift(2).bfill()
            df['speed_lag_4'] = df['current_speed_kmh'].shift(4).bfill() # 1h lag (15min * 4)
            df['congestion_lag_1'] = df['congestion_index'].shift(1).bfill()
            df['congestion_lag_2'] = df['congestion_index'].shift(2).bfill()
            
        return df

if __name__ == "__main__":
    import os
    from preprocessing import DataPreprocessor
    
    raw_path = os.path.join(os.path.dirname(__file__), "..", "data", "raw_traffic_weather.csv")
    if os.path.exists(raw_path):
        df_raw = pd.read_csv(raw_path)
        processor = DataPreprocessor()
        df_clean = processor.transform(df_raw)
        
        fe = FeatureEngineer()
        df_feat = fe.extract_features(df_clean)
        print("Feature engineering complete! Shape:", df_feat.shape)
        print("Extracted columns:", [c for c in df_feat.columns if 'sin' in c or 'lag' in c or 'impact' in c])
