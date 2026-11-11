"""Merge the visual card revision without replacing newer career destinations.

Pure XML transforms. Caller backs up and installs layouts/textures separately;
no save, DB, executable, FSW stadium mapping or navigation flow is edited.
"""
from collections import Counter
from copy import deepcopy
import re
import xml.etree.ElementTree as ET

CAREER = 'data/ui/layout/careermanagerhubcfg.xml'
FRONTEND = 'data/ui/layout/mainhubcfg.xml'
OVERLAY = 'ModCarrerMode/source/native_mods/career_overlay/layout/careermanagerhubcfg.xml'
FRONTEND_SOURCE = 'ModCarrerMode/source/native_mods/frontend_customization/layout/mainhubcfg.xml'


def events(node):
    return Counter(n.get('DESTINATION') for n in node.iter() if n.get('DESTINATION'))


def card(root, name):
    found = [t for t in root.iter('tile') if t.find('tileid').get('NAME') == name]
    if len(found) != 1:
        raise ValueError('Card não identificado: '+name)
    return found[0]


def slides(tile):
    return [(tile.find('main_tile'), tile)] + [(n, n) for n in tile if n.tag.startswith('subtile')]


def merge_career(raw, donor):
    """Only the two transfer cards; newer rankings/calendar remain byte exact."""
    before, reference = ET.fromstring(raw), ET.fromstring(donor)
    changed = {}
    labels = dict(EnterPlayerSearch='BUSCAR JOGADOR', EnterShoppingList='INSTRUÇÕES',
                  EnterViewShortlist='PRÉ-LISTA', EnterSellPlayers='VENDER JOGADOR',
                  EnterNegHistory='NEGOCIAÇÕES', Server16EnterManagerMarket='M. TÉCNICOS')
    for name in ('SHOPPING_LIST', 'SERVER16_MANAGER_MARKET'):
        current, incoming = card(before, name), card(reference, name)
        if events(current) != events(incoming):
            raise ValueError('A revisão altera os destinos do card '+name)
        incoming_slides = {n.get('DESTINATION'): (n, owner) for n, owner in slides(incoming)}
        for page, owner in slides(current):
            target = page.get('DESTINATION')
            other, other_owner = incoming_slides[target]
            if other.get('BG_ICON'):
                page.set('BG_ICON', other.get('BG_ICON'))
            title = owner.find("data[@ID='TITLE']")
            title.attrib.update(PARAM=labels[target], TRANSLATE='FALSE', FORMAT='HS',
                                X='18', Y='18', WIDTH='382', HEIGHT='45')
            # Reserve the right-hand side for the existing, original icon.
            for field in owner.findall('data'):
                if field.get('TYPE') != 'text':
                    continue
                field.attrib.pop('REL_TARGET', None)
                field.attrib.pop('REL_Y', None)
                field.attrib.update(X='18', Y='72', WIDTH='260', HEIGHT='108')
        changed[name] = current

    text = raw.decode('utf-8-sig')
    def replace(match):
        node = ET.fromstring(match.group())
        name = node.find('tileid').get('NAME')
        return ET.tostring(changed[name], encoding='unicode').strip() if name in changed else match.group()
    result = re.sub(r'<tile\b[^>]*>.*?</tile>', replace, text, flags=re.S).encode('utf8')
    after = ET.fromstring(result)
    if events(before) != events(after):
        raise ValueError('Destinos da carreira foram alterados')
    return result if result != raw else raw


def personalize(raw):
    """Keep native routes/IDs; move two cards up and split player actions."""
    match = re.search(rb'<panel_4\b[^>]*>.*?</panel_4>', raw, re.S)
    if not match:
        raise ValueError('Aba Personalizar não encontrada')
    panel = ET.fromstring(match.group())
    before = events(panel)
    by_id = {t.find('tileid').get('tileid'): t for t in panel.findall('tile')}
    if '304' not in by_id and '48' not in by_id and all(k in by_id for k in ('322','323')):
        return raw
    for key in ('304','48','368','1216','320'):
        if key not in by_id:
            raise ValueError('Layout Personalizar incompatível: '+key)
    panel.remove(by_id['304'])
    panel.remove(by_id['48'])
    for key, x in (('368',965),('1216',1393)):
        by_id[key].find('settings').attrib.update(X=str(x), Y='278')

    player = by_id['320']
    actions = [deepcopy(n) for n in player if n.tag.startswith('subtile')]
    if [n.get('DESTINATION') for n in actions] != ['EditPlayerAdvance','DeletePlayerAdvance']:
        raise ValueError('Carrossel de jogadores incompatível')
    player.find('settings').attrib.update(FILE_PATH='TILE',ENABLE_CYCLING='FALSE',X='109',Y='598')
    player.find('number_of_subtiles').set('LENGTH','0')
    for node in list(player):
        if node.tag.startswith('subtile'):
            player.remove(node)
    index = list(panel).index(player)+1
    for offset, (source, x) in enumerate(zip(actions,(537,965))):
        tile = ET.Element('tile')
        ET.SubElement(tile,'tileid',tileid=source.get('ID'),NAME='',PARAM='')
        ET.SubElement(tile,'settings',FILE_PATH='TILE',WIDTH='418',HEIGHT='310',
                      X=str(x),Y='598',ENABLE_CYCLING='FALSE')
        main = deepcopy(source);main.tag='main_tile'
        fields=list(main.findall('data'))
        for field in fields:
            main.remove(field)
        tile.append(main);ET.SubElement(tile,'number_of_subtiles',LENGTH='0')
        tile.extend(fields);panel.insert(index+offset,tile)
    panel.find('entries').set('numberoftiles',str(len(panel.findall('tile'))))
    expected=before.copy();expected.subtract(events(by_id['304']));expected.subtract(events(by_id['48']))
    if +expected != events(panel):
        raise ValueError('Uma ação funcional foi perdida ou duplicada')
    ids=[t.find('tileid').get('tileid') for t in panel.findall('tile')]
    if len(ids)!=len(set(ids)):
        raise ValueError('IDs de cards duplicados')
    ET.indent(panel,space='  ')
    replacement=ET.tostring(panel,encoding='utf-8')
    return raw[:match.start()]+replacement+raw[match.end():]
