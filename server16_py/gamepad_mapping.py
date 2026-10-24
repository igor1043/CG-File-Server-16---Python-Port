"""Pure per-device mapping/calibration; SDL and virtual-pad calls stay in one worker."""
from __future__ import annotations

BUTTONS = ('A', 'B', 'X', 'Y', 'LEFT_SHOULDER', 'RIGHT_SHOULDER', 'BACK',
           'START', 'LEFT_THUMB', 'RIGHT_THUMB', 'DPAD_UP', 'DPAD_DOWN', 'DPAD_LEFT', 'DPAD_RIGHT')
STEPS = tuple((key, label) for key, label in zip(BUTTONS, (
    'A / botão inferior', 'B / botão à direita', 'X / botão à esquerda', 'Y / botão superior',
    'L1 / LB', 'R1 / RB', 'Select / Back', 'Start / Menu', 'Clique do analógico esquerdo',
    'Clique do analógico direito', 'Direcional para cima', 'Direcional para baixo',
    'Direcional para a esquerda', 'Direcional para a direita'))) + (
    ('LX', 'Analógico esquerdo para a direita'), ('LY', 'Analógico esquerdo para cima'),
    ('RX', 'Analógico direito para a direita'), ('RY', 'Analógico direito para cima'),
    ('LT', 'L2 / LT até o fim'), ('RT', 'R2 / RT até o fim'))


def raw_joystick(joystick):
    return {'buttons': [bool(joystick.get_button(i)) for i in range(joystick.get_numbuttons())],
            'axes': [float(joystick.get_axis(i)) for i in range(joystick.get_numaxes())],
            'hats': [tuple(joystick.get_hat(i)) for i in range(joystick.get_numhats())]}


def binding_value(raw, binding):
    try:
        kind, index = binding['kind'], int(binding['index'])
        if index < 0: return 0.0
        if kind == 'button': return float(bool(raw['buttons'][index]))
        if kind == 'hat': return float(raw['hats'][index][binding['component']] * binding['sign'])
        if kind == 'axis':
            span = float(binding['extent']) - float(binding['center'])
            return max(-1., min(1., (float(raw['axes'][index]) - binding['center']) / span)) if abs(span) > .2 else 0.
    except (KeyError, IndexError, TypeError, ValueError): pass
    return 0.


def mapped_state(raw, mapping):
    bindings = mapping.get('bindings', {})
    deadzone = max(.02, min(.4, float(mapping.get('deadzone', .12))))
    def value(key): return binding_value(raw, bindings.get(key, {}))
    def stick(key):
        v=value(key)
        return 0. if abs(v) <= deadzone else (1 if v > 0 else -1) * (abs(v)-deadzone)/(1-deadzone)
    return {'buttons': {'XUSB_GAMEPAD_'+key: value(key)>.5 for key in BUTTONS},
            'left_stick': (stick('LX'), stick('LY')), 'right_stick': (stick('RX'), stick('RY')),
            'left_trigger': max(0., value('LT')), 'right_trigger': max(0., value('RT'))}


class MappingCapture:
    def __init__(self):
        self.index=0; self.bindings={}; self.neutral=None; self.released=False

    @property
    def done(self): return self.index >= len(STEPS)

    def skip(self):
        if not self.done: self.index += 1
        self.released=False

    def observe(self, raw):
        if raw is None or self.done: return False
        if self.neutral is None:
            self.neutral={'buttons': list(raw.get('buttons', [])), 'axes': list(raw.get('axes', [])),
                          'hats': list(raw.get('hats', []))}
            return False
        candidates=[]
        analog = STEPS[self.index][0] in ('LX','LY','RX','RY')
        for i, pressed in enumerate(raw.get('buttons', [])):
            if pressed: candidates.append({'kind':'button','index':i})
        for i, hat in enumerate(raw.get('hats', [])):
            for j, v in enumerate(hat):
                if v: candidates.append({'kind':'hat','index':i,'component':j,'sign':1 if v>0 else -1})
        for i, v in enumerate(raw.get('axes', [])):
            center=self.neutral['axes'][i] if i < len(self.neutral['axes']) else 0.
            if abs(v-center) > .6: candidates.append({'kind':'axis','index':i,'center':center,'extent':v})
        if not candidates:
            self.released=True
            return False
        if not self.released: return False
        if analog: candidates=[b for b in candidates if b['kind']=='axis']
        if not candidates: return False
        self.bindings[STEPS[self.index][0]]=candidates[0]
        self.index += 1; self.released=False
        return True

    def result(self): return {'version':1, 'deadzone':.12, 'bindings':dict(self.bindings)}
