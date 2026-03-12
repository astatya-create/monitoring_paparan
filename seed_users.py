from database import db

# GANTI daftar user ini sesuai tim kamu (15 orang)
users = [
    {"username": "admin", "password": "Admin123$", "role": "admin"},
    {"username": "catur", "password": "Catur123$", "role": "atasan"},
    {"username": "agung", "password": "Agung123$", "role": "pic"},
    {"username": "asto", "password": "Asto123$", "role": "pic"},
    {"username": "nauval", "password": "Nauval123$", "role": "pic"},
    {"username": "devin", "password": "Devin123$", "role": "pic"},
    {"username": "farid", "password": "Farid123$", "role": "pic"},
    {"username": "intan", "password": "Intan123$", "role": "pic"},
    {"username": "gunawan", "password": "Gunawan123$", "role": "pic"},
    {"username": "afi", "password": "Afi123$", "role": "pic"},
    {"username": "romadhon", "password": "Romadhon123$", "role": "pic"},
    {"username": "ginanjar", "password": "Ginanjar123$", "role": "pic"},  
    {"username": "danang", "password": "Danang123$", "role": "pic"}, 
    {"username": "yuwono", "password": "Yuwono123$", "role": "pic"}
]

for user in users:
    db.collection("users").add(user)

print("Users inserted to Firestore")

