from database import db

# GANTI daftar user ini sesuai tim kamu (15 orang)
users = [
    {"username": "admin", "password": "admin123", "role": "admin"},
    {"username": "catur", "password": "catur123", "role": "atasan"},
    {"username": "agung", "password": "agung123", "role": "pic"},
    {"username": "asto", "password": "asto123", "role": "pic"},
    {"username": "nauval", "password": "nauval123", "role": "pic"},
    {"username": "devin", "password": "devin123", "role": "pic"},
    {"username": "farid", "password": "farid123", "role": "pic"},
    {"username": "intan", "password": "intan123", "role": "pic"},
    {"username": "gunawan", "password": "gunawan123", "role": "pic"},
    {"username": "afi", "password": "afi123", "role": "pic"},
    {"username": "romadhon", "password": "romadhon123", "role": "pic"},
    {"username": "ginanjar", "password": "ginanjar123", "role": "pic"},  
    {"username": "danang", "password": "danang123", "role": "pic"}, 
    {"username": "yuwono", "password": "yuwono123", "role": "pic"}
]

for user in users:
    db.collection("users").add(user)

print("Users inserted to Firestore")

