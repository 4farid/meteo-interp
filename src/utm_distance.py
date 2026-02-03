import pyproj

P = pyproj.Proj(proj='utm', zone=32, ellps='WGS84', preserve_units=True)
G = pyproj.Geod(ellps='WGS84')

def LonLat_To_XY(Lon, Lat):
    return P(Lon, Lat)


x = LonLat_To_XY(12.4924, 41.8902)  # Longitude and Latitude of the Colosseum in Rome
print(f"UTM Coordinates: {x}")
