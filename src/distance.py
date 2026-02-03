import pyproj

G = pyproj.Geod(ellps='WGS84')

def distance(Lat1, Lon1, Lat2, Lon2):
    return G.inv(Lon1, Lat1, Lon2, Lat2)[2]