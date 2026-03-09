import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# load service account
cred = credentials.Certificate("serviceAccountKey.json")

# initialize firebase
firebase_admin.initialize_app(cred)

# connect firestore
db = firestore.client()

def test_connection():
    doc_ref = db.collection("test").document("connection")
    doc_ref.set({
        "status": "connected"
    })