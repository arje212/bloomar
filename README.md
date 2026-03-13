# BloomAR — Django Web App

## Setup
```bash
pip install -r requirements.txt
python manage.py runserver
```
Then open http://localhost:8000

## Flow
1. **Home** `/` — Landing page, saved bouquets
2. **Camera** `/camera/` — Scan a flower (uses webcam + /api/detect/)
3. **Editor** `/editor/` — Add/edit flowers, ribbon, wrapper
4. **AR Preview** `/ar-preview/` — Draggable bouquet overlay with live customization

## Replacing the mock detector
Edit `core/views.py` → `detect_flower()` to call your real ML model or an external API.

## Production
- Set `DEBUG = False` and a real `SECRET_KEY` in settings.py
- Run `collectstatic` and serve with gunicorn + nginx
