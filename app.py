import os, re
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, send_from_directory
import requests
from lxml import etree

app = Flask(__name__)
ZONE = ZoneInfo('America/Los_Angeles')
SCHOOL = 'VintageParkwayElementary'


def parse_menu(raw, date):
    # A browser copy may include a non-XML introductory sentence; live XML should not.
    start = raw.find(b'<School ')
    if start < 0:
        raise ValueError('MealViewer did not return a School XML document')
    root = etree.fromstring(raw[start:], etree.XMLParser(recover=True, resolve_entities=False, no_network=True))
    schedules = root.xpath('//*[local-name()="MenuSchedules"]/*[local-name()="MenuSchedule"]')
    out = {'breakfast': [], 'lunch': []}
    for schedule in schedules:
        keys = schedule.xpath('./*[local-name()="DateInformation"]/*[local-name()="DateKey"]/text()')
        if not keys or keys[0] != date.replace('-', ''):
            continue
        for block in schedule.xpath('./*[local-name()="MenuBlocks"]/*[local-name()="MenuBlock"]'):
            names = block.xpath('./*[local-name()="BlockName"]/text()')
            block_name = names[0].strip() if names else ''
            if block_name.lower() not in ('breakfast', 'regular breakfast', 'lunch'):
                continue
            meal = 'lunch' if block_name.lower() == 'lunch' else 'breakfast'
            for item in block.xpath('.//*[local-name()="FoodItemList"]/*[local-name()="Data"]/*[local-name()="FoodItem"]'):
                names = item.xpath('./*[local-name()="Item_Name"]/text()')
                visible = item.xpath('./*[local-name()="MVS_Visible"]/text()')
                if not names or (visible and visible[0].lower() != 'true'):
                    continue
                name = re.sub(r'\s+', ' ', names[0]).strip()
                if name and name not in out[meal]:
                    out[meal].append(name)
    return out

@app.get('/')
def index():
    return send_from_directory('static', 'index.html')

@app.get('/api/menu')
def menu():
    date = datetime.now(ZONE).strftime('%Y-%m-%d')
    url = f'https://api.mealviewer.com/api/v4/school/{quote(SCHOOL, safe='')}/{date}/{date}/'
    try:
        response = requests.get(url, headers={'Accept':'application/xml, text/xml;q=0.9, */*;q=0.5', 'User-Agent':'SchoolMenuDisplay/1.0'}, timeout=20)
        response.raise_for_status()
        data = parse_menu(response.content, date)
        return jsonify({'date':date, **data, 'source':'MealViewer', 'updated':datetime.now(ZONE).isoformat()}), 200, {'Cache-Control':'no-store'}
    except (requests.RequestException, ValueError, etree.XMLSyntaxError) as exc:
        app.logger.warning('Menu feed error: %s', exc)
        return jsonify({'date':date, 'breakfast':[], 'lunch':[], 'error':'Live MealViewer menu unavailable; check source or server logs'}), 503, {'Cache-Control':'no-store'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
