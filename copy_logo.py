"""
One-off: copy the UniPi horizontal logo (emblem + text) into static/images for the navbar.
Run from project root:  python copy_logo.py
"""
import shutil
import os

# Cursor assets path for the logo you provided (Πανεπιστήμιο Πειραιώς / University of Piraeus)
src = r"C:\Users\xrist\.cursor\projects\c-Users-xrist-Documents-University-Shi-cs-unipi\assets\c__Users_xrist_AppData_Roaming_Cursor_User_workspaceStorage_db8e3be405a05c6e878220251b9642b8_images_logopapei3-1f3644cc-0029-4d12-8d43-e33393380068.png"
base = os.path.dirname(os.path.abspath(__file__))
dest = os.path.join(base, "static", "images", "unipi-logo.png")
os.makedirs(os.path.dirname(dest), exist_ok=True)
if not os.path.isfile(src):
    print("Source not found. Copy the logo image manually to:", dest)
    raise SystemExit(1)
shutil.copy2(src, dest)
print("Logo copied to:", dest)
