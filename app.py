from flask import Flask, render_template, jsonify, request, make_response, send_from_directory
from bs4 import BeautifulSoup
from flask_cors import CORS
import re
import cloudscraper
import logging
from datetime import datetime, timedelta
import threading
import time
import random
from urllib.parse import urlparse
import os

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

video_cache = {}
CACHE_DURATION = 0  # 5 minutes cache
REFRESH_INTERVAL = 1800  # 30 minutes auto-refresh
MAX_RETRIES = 3

TARGET_SITES = [
    {"name": "Main Site", "url": "https://www.xv-ru.com/?k=sissy&sort=random&typef=gay"},
    {"name": "Gay Videos", "url": "https://www.xv-ru.com/?k=gay&sort=random&typef=gay"},
    {"name": "Trans Videos", "url": "https://www.xv-ru.com/?k=trans&sort=random&typef=trans"},
    {"name": "Lesbian Videos", "url": "https://www.xv-ru.com/?k=lesbian&sort=random&typef=lesbian"},
    {"name": "Bisexual Videos", "url": "https://www.xv-ru.com/?k=bisexual&sort=random&typef=bisexual"}
]

def parse_main_page(page=0, site_index=0):
    """Парсинг главной страницы с поддержкой пагинации и множественных сайтов"""
    try:
        print("="*60)

        # Выбираем сайт для парсинга
        site_url = TARGET_SITES[site_index]["url"]

        # Формируем URL с параметром страницы
        if page > 0:
            url = f"{site_url}&p={page}"
        else:
            url = site_url

        print(f"Запрос к {url}")

        # Создаем scraper с случайными заголовками для обхода защиты
        headers = {
            'User-Agent': random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            ]),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }

        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, headers=headers, timeout=15)

        print(f"Статус: {response.status_code}")

        soup = BeautifulSoup(response.content, 'html.parser')
        videos = []

        # Ищем все видео блоки
        video_blocks = soup.find_all('div', class_='thumb-block')
        print(f"✓ Найдено {len(video_blocks)} видео блоков")

        for block in video_blocks:
            try:
                # Ссылка на видео
                link = block.find('a', href=re.compile(r'/video'))
                if not link:
                    continue

                href = link.get('href', '')

                # ID из URL
                video_id_match = re.search(r'/video\.([a-z0-9]+)/', href)
                if not video_id_match:
                    continue

                video_id = video_id_match.group(1)

                # НАЗВАНИЕ из title атрибута ссылки в thumb-under
                title_link = block.find('p', class_='title')
                title = ""
                if title_link:
                    title_a = title_link.find('a')
                    if title_a:
                        # Берем title атрибут
                        title = title_a.get('title', '')
                        # Убираем длительность из title если есть
                        title = re.sub(r'\s*<span class="duration">.*?</span>\s*$', '', title)

                # Если title не найден, пробуем текст
                if not title:
                    if title_link:
                        title_a = title_link.find('a')
                        if title_a:
                            title_text = title_a.get_text(strip=True)
                            # Убираем длительность из конца
                            title = re.sub(r'\s+\d+\s+(мин\.|сек\.|ч\.).*$', '', title_text)

                if not title:
                    title = f"Video {video_id}"

                # Полный URL
                video_url = site_url.split('?')[0].rstrip('/') + href if href.startswith('/') else href

                # Thumbnail
                thumbnail = ""
                img = block.find('img')
                if img:
                    thumbnail = (img.get('data-src') or
                                img.get('data-thumb_url') or
                                img.get('src') or "")

                    if thumbnail:
                        # protocol-relative (//example.com/img.jpg)
                        if thumbnail.startswith('//'):
                            thumbnail = 'https:' + thumbnail
                        # root-relative (/images/img.jpg)
                        elif thumbnail.startswith('/'):
                            base = site_url.split('?')[0].rstrip('/')
                            thumbnail = base + thumbnail
                        # relative (images/img.jpg)
                        elif not thumbnail.startswith('http'):
                            base = f"{urlparse(site_url).scheme}://{urlparse(site_url).netloc}"
                            thumbnail = base.rstrip('/') + '/' + thumbnail

                # Длительность
                duration = "00:00"
                dur_span = block.find('span', class_='duration')
                if dur_span:
                    duration = dur_span.get_text(strip=True)

                # Попробуем получить количество просмотров
                views = "0"
                views_elem = block.find('span', class_='views')
                if views_elem:
                    views_text = views_elem.get_text(strip=True)
                    # Извлекаем число просмотров
                    views_match = re.search(r'(\d+(?:\.\d+)?[KMB]?)', views_text)
                    if views_match:
                        views = views_match.group(1)

                # Добавляем информацию о сайте
                videos.append({
                    'id': video_id,
                    'title': title.strip(),
                    'page_url': video_url,
                    'thumbnail': thumbnail,
                    'duration': duration,
                    'views': views,
                    'source_site': TARGET_SITES[site_index]["name"],
                    'added_at': datetime.utcnow().isoformat()
                })

                print(f"✓ {video_id}: {title[:80]}")

            except Exception as e:
                print(f"⚠ Ошибка парсинга блока: {e}")
                continue

        print(f"ИТОГО: {len(videos)} видео на странице {page} с {TARGET_SITES[site_index]['name']}")
        return videos

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_video_embed_url(video_id):
    """Получение iframe URL для встраивания"""
    embed_url = f"https://www.xv-ru.com/embedframe/{video_id}"
    print(f"✓ Embed URL: {embed_url}")

    return {
        'type': 'iframe',
        'url': embed_url
    }

def auto_refresh_cache():
    """Автоматическое обновление кеша"""
    while True:
        time.sleep(REFRESH_INTERVAL)
        print("\n🔄 Автообновление кеша...")
        for site_index in range(len(TARGET_SITES)):
            parse_main_page(0, site_index)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/logo.png')
def logo_png():
    # Serve the logo file located in the project root
    import os
    root = os.getcwd()
    return send_from_directory(root, 'logo.png')

@app.route('/api/videos')
def get_videos():
    import time

    # Получаем номер страницы из параметров запроса
    page = request.args.get('page', 0, type=int)
    site_index = request.args.get('site', 0, type=int)
    sort_by = request.args.get('sort', 'random')  # random, date, views

    # Проверяем корректность индекса сайта
    if site_index >= len(TARGET_SITES):
        site_index = 0

    cache_key = f'page_{page}_site_{site_index}'
    current_time = time.time()

    # Проверяем кеш для конкретной страницы
    if cache_key not in video_cache:
        video_cache[cache_key] = {'data': [], 'timestamp': 0}

    if current_time - video_cache[cache_key]['timestamp'] > CACHE_DURATION or not video_cache[cache_key]['data']:
        print(f"\n🔄 Обновление кеша для страницы {page}, сайт {TARGET_SITES[site_index]['name']}...")
        video_cache[cache_key]['data'] = parse_main_page(page, site_index)
        video_cache[cache_key]['timestamp'] = current_time
    else:
        remaining = int(CACHE_DURATION - (current_time - video_cache[cache_key]['timestamp']))
        print(f"✓ Кеш страницы {page} сайта {TARGET_SITES[site_index]['name']} ({remaining} сек, видео: {len(video_cache[cache_key]['data'])})")

    # Сортировка видео
    videos = video_cache[cache_key]['data'].copy()

    if sort_by == 'date':
        videos.sort(key=lambda x: x.get('added_at', ''), reverse=True)
    elif sort_by == 'views':
        def extract_views(views_str):
            if 'K' in views_str:
                return float(views_str.replace('K', '')) * 1000
            elif 'M' in views_str:
                return float(views_str.replace('M', '')) * 1000000
            elif 'B' in views_str:
                return float(views_str.replace('B', '')) * 1000000000
            else:
                return int(views_str) if views_str.isdigit() else 0

        videos.sort(key=lambda x: extract_views(x.get('views', '0')), reverse=True)
    elif sort_by == 'random':
        random.shuffle(videos)

    resp = make_response(jsonify({
        'videos': videos,
        'page': page,
        'total': len(videos),
        'site_info': TARGET_SITES[site_index],
        'sort_by': sort_by
    }))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/api/sites')
def get_sites():
    """API endpoint для получения списка доступных сайтов"""
    return jsonify(TARGET_SITES)

@app.route('/api/video/<video_id>')
def get_video_details(video_id):
    # Ищем видео в кеше всех страниц
    video = None
    for cache_key in video_cache:
        if video_cache[cache_key]['data']:
            video = next((v for v in video_cache[cache_key]['data'] if v['id'] == video_id), None)
            if video:
                break

    # Если не найдено в кеше, парсим первую страницу каждого сайта
    if not video:
        for site_index in range(len(TARGET_SITES)):
            videos = parse_main_page(0, site_index)
            video = next((v for v in videos if v['id'] == video_id), None)
            if video:
                break

    if video:
        embed_data = get_video_embed_url(video_id)
        video['embed'] = embed_data
        resp = make_response(jsonify(video))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp

    resp = make_response(jsonify({'error': 'Video not found'}), 404)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/api/refresh')
def refresh():
    # Очищаем весь кеш
    video_cache.clear()
    videos = []

    # Парсим все сайты
    for site_index in range(len(TARGET_SITES)):
        videos.extend(parse_main_page(0, site_index))

    # Добавляем embed для первых 3 видео
    for video in videos[:3]:
        video['embed'] = get_video_embed_url(video['id'])

    resp = make_response(jsonify({
        'total': len(videos),
        'videos': videos[:3],
        'message': f'Cleared cache and refreshed {len(videos)} videos from {len(TARGET_SITES)} sites'
    }))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/api/search')
def search_videos():
    """Поиск видео по ключевому слову"""
    query = request.args.get('q', '').strip().lower()
    if not query:
        return jsonify({'error': 'Query parameter required'}), 400

    # Ищем видео во всех закешированных данных
    results = []
    for cache_key in video_cache:
        if video_cache[cache_key]['data']:
            for video in video_cache[cache_key]['data']:
                if query in video['title'].lower() or query in video['id'].lower():
                    results.append(video)

    # Если не нашли в кеше, делаем новый поиск
    if not results:
        for site_index in range(len(TARGET_SITES)):
            videos = parse_main_page(0, site_index)
            for video in videos:
                if query in video['title'].lower() or query in video['id'].lower():
                    results.append(video)

    return jsonify({
        'query': query,
        'results': results[:20],  # Ограничиваем результаты
        'total': len(results)
    })

@app.route('/api/stats')
def get_stats():
    """API endpoint для получения статистики"""
    total_videos = 0
    cached_pages = len(video_cache)

    for cache_key in video_cache:
        total_videos += len(video_cache[cache_key]['data'])

    # Определяем время последнего обновления
    last_update = 0
    for cache_key in video_cache:
        if video_cache[cache_key]['timestamp'] > last_update:
            last_update = video_cache[cache_key]['timestamp']

    last_update_str = datetime.fromtimestamp(last_update).strftime('%Y-%m-%d %H:%M:%S') if last_update > 0 else 'Never'

    return jsonify({
        'total_cached_videos': total_videos,
        'cached_pages': cached_pages,
        'last_update': last_update_str,
        'cache_duration': CACHE_DURATION,
        'sites_count': len(TARGET_SITES)
    })

@app.route('/api/trending')
def get_trending():
    """API endpoint для получения трендовых видео"""
    trending_videos = []

    # Получаем видео из всех сайтов
    for site_index in range(len(TARGET_SITES)):
        if f'page_0_site_{site_index}' in video_cache:
            videos = video_cache[f'page_0_site_{site_index}']['data']
            # Сортируем по количеству просмотров
            def extract_views(views_str):
                if 'K' in views_str:
                    return float(views_str.replace('K', '')) * 1000
                elif 'M' in views_str:
                    return float(views_str.replace('M', '')) * 1000000
                elif 'B' in views_str:
                    return float(views_str.replace('B', '')) * 1000000000
                else:
                    return int(views_str) if views_str.isdigit() else 0

            videos.sort(key=lambda x: extract_views(x.get('views', '0')), reverse=True)
            trending_videos.extend(videos[:5])  # Берем топ 5 с каждого сайта

    # Возвращаем топ 20 самых просматриваемых видео
    trending_videos.sort(key=lambda x: extract_views(x.get('views', '0')), reverse=True)

    return jsonify({
        'trending_videos': trending_videos[:20],
        'total': len(trending_videos)
    })

if __name__ == '__main__':
    print("="*60)
    print("🚀 http://localhost:5000")
    print("🔄 http://localhost:5000/api/refresh")
    print("🔍 http://localhost:5000/api/search?q=term")
    print("📊 http://localhost:5000/api/stats")
    print("🌐 http://localhost:5000/api/sites")
    print("🔥 http://localhost:5000/api/trending")
    print("="*60)

    # Запускаем автообновление кеша в отдельном потоке
    refresh_thread = threading.Thread(target=auto_refresh_cache, daemon=True)
    refresh_thread.start()

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
