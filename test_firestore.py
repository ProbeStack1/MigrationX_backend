"""Quick test script to verify Firestore connection"""
from google.cloud import firestore
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

print("=" * 60)
print("Firestore Connection Test")
print("=" * 60)

# Check if credentials path is set
cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
if cred_path:
    print("[OK] GOOGLE_APPLICATION_CREDENTIALS is set")
    print(f"  Path: {cred_path}")
    
    # Check if file exists
    if os.path.exists(cred_path):
        print("[OK] Credentials file exists")
    else:
        print("[ERROR] Credentials file NOT found at: {cred_path}")
        print("  Please check the path in your .env file")
else:
    print("[ERROR] GOOGLE_APPLICATION_CREDENTIALS not set")
    print("  Please add it to your .env file")

print("\n" + "-" * 60)
print("Testing Firestore connection...")
print("-" * 60)

try:
    # Try to connect to Firestore
    db = firestore.Client()
    print("[OK] Firestore client created successfully!")
    
    # Test write
    print("\nTesting write operation...")
    doc_ref = db.collection('test').document('connection_test')
    doc_ref.set({
        'status': 'connected',
        'timestamp': 'test',
        'message': 'Firestore is working correctly!'
    })
    print("[OK] Test write successful!")
    
    # Test read
    print("\nTesting read operation...")
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        print("[OK] Test read successful!")
        print(f"  Data: {data}")
    else:
        print("[ERROR] Document not found after write")
    
    # Clean up test document
    doc_ref.delete()
    print("\n[OK] Test document cleaned up")
    
    print("\n" + "=" * 60)
    print("[SUCCESS] ALL TESTS PASSED! Firestore is configured correctly.")
    print("=" * 60)
    
except Exception as e:
    print(f"\n[ERROR] Error connecting to Firestore: {e}")
    print("\nTroubleshooting:")
    print("1. Verify GOOGLE_APPLICATION_CREDENTIALS path in .env file")
    print("2. Check that the JSON file exists and is readable")
    print("3. Ensure the service account has Firestore permissions")
    print("4. Verify Firestore API is enabled in your GCP project")
    print("\n" + "=" * 60)

