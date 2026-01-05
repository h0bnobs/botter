from math import cos
from math import radians

import requests


def get_nearby_aircraft(lat, lon, radius_km=10):
    lat_diff = radius_km / 111
    lon_diff = radius_km / (111 * abs(cos(radians(lat))))

    url = "https://opensky-network.org/api/states/all"
    params = {
        "lamin": lat - lat_diff,
        "lamax": lat + lat_diff,
        "lomin": lon - lon_diff,
        "lomax": lon + lon_diff
    }

    resp = requests.get(url, params=params)
    return resp.json().get('states', [])

# t = get_nearby_aircraft(51.254038, 0.437667)
# # 51.254038, 0.437667
# print(t)
