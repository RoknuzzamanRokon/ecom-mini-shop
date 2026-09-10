import geocoder

g = geocoder.ip('me')

print("Latitude:", g.latlng[0])
print("Longitude:", g.latlng[1])
print("City:", g.city)
print("State:", g.state)
print("Country:", g.country)
print("Postal Code:", g.postal)
print("Address:", g.address)
print("Organization:", g.org)


print("IP:", g.ip)
print("Organization:", g.org)
print("City:", g.city)
print("Country:", g.country)
print("Lat/Lon:", g.latlng)
