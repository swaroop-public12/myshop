# Dress Catalogue App

A lightweight online dress catalogue with:
- Price, discount, and expected price calculation
- "Sold" toggle (greys out the image)
- "Interested" and "Ask Price" buttons
- Admin panel to update items without editing Google Sheets manually
- Google Sheets backend for storage

---

## 1. Features
- **Public View**:  
  - View dresses with images, prices, and discounts
  - Click "Interested" to show popularity
  - Click "Ask Price" to open WhatsApp with product details
  - Sold items are greyed out

- **Admin View** (password-protected):  
  - Add, edit, delete items
  - Mark items as sold/unsold
  - All changes update Google Sheets instantly

---

## 2. Requirements

- Python 3.8+
- Google account (for Google Sheets backend)
- GitHub account (for Streamlit Cloud hosting)

---

## 3. Setup Instructions

### Step 1 — Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/dress-catalogue.git
cd dress-catalogue
