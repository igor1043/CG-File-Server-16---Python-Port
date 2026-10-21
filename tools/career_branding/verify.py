"""Exercise the generated native ActionScript lifecycle in a bounded local VM."""
from pathlib import Path
import argparse
import copy
import json
import struct
import sys


def verify(output):
    from formats import AptFile, BigFile, Reader
    from apt_actions import Actions
    from apt_vm import VM, Object, Native
    import build

    calls = []
    def native(name, owner, args):
        calls.append((name, tuple(args)))
        if name == 'original.ChangeWidgetState':
            owner.set('_visible', args[0] != 0); owner.set('_alpha', 100)
        if name == 'original.InitializeLayout':
            owner.set('_visible', True); owner.set('_alpha', 100)

    class NativeGlobalVM(VM):
        def run(self, code, *args, **kwargs):
            # The shared preview VM aliases 0x58 and 0x71. FIFA does not:
            # 0x58 constructs a string whose contents are "_global".
            # Preserve this difference even for recursively invoked functions.
            native_code = []
            for instruction in code:
                if instruction.op == 88:
                    instruction = copy.copy(instruction)
                    instruction.op, instruction.value = 161, '_global'
                native_code.append(instruction)
            return super().run(native_code, *args, **kwargs)

    vm = NativeGlobalVM(native)
    movies = []
    for relative in ('data/ui/game/components/careercomponents/careerhubwidget.big',
                     'data/ui/pow/components/easfcwidget.big',
                     'data/ui/game/widgets/mainhubwidget.big'):
        actions = Actions(AptFile(BigFile(output / relative))).read_all()
        assert not actions.errors
        # The real FIFA loader dereferences Function2.name even for anonymous
        # functions. A null pointer passes the lenient local decoder but crashes
        # the native constructor (observed at FIFA16+0x3a5e4f2).
        def native_function_headers(instructions):
            for instruction in instructions:
                if instruction.op in (142, 155):
                    assert all(i.op != 0 for i in instruction.body), \
                        'Embedded End opcode stops native relocation of subsequent functions'
                if instruction.op == 142:
                    reader = Reader(actions.apt.data, instruction.offset + 1, 8)
                    name = reader.ptr()
                    assert 0 < name < len(actions.apt.data), 'Null/invalid native Function2 name'
                    reader.string(name)
                    reader.pos = (reader.pos + 3) // 4 * 4
                    count = reader.i(); reader.read('h'); reader.read('H')
                    parameters = reader.ptr()
                    assert 0 < parameters < len(actions.apt.data), 'Null/invalid native parameter table'
                    assert parameters + count * 16 <= len(actions.apt.data)
                if instruction.body: native_function_headers(instruction.body)
        for block in actions.cache.values(): native_function_headers(block)
        movies.append(actions)
        for block in actions.cache.values():
            if block[0].op == 136: vm.run(block, vm.global_, vm.global_)
    career = vm.path('.'.join(build.CAREER)); easfc = vm.path('.'.join(build.EASFC))
    main = vm.path('.'.join(build.MAIN))
    original_methods = [(career, method) for method in ('InitComponents', 'SetData', 'Shutdown')]
    original_methods += [(easfc, method) for method in ('InitializeLayout', 'ChangeWidgetState')]
    original_methods += [(main, 'Shutdown'), (main, 'Publish')]
    # Replaying native class initialization must not wrap a wrapper recursively.
    before = [proto.get('Server16Original' + method) for proto, method in original_methods]
    wrappers = [proto.get(method) for proto, method in original_methods]
    for actions in movies:
        for block in actions.cache.values():
            if block[0].op == 136: vm.run(block, vm.global_, vm.global_)
    assert before == [proto.get('Server16Original' + method) for proto, method in original_methods]
    assert wrappers == [proto.get(method) for proto, method in original_methods]
    for proto, method in original_methods: proto.set('Server16Original' + method, Native('original.' + method))

    manager = Object()
    vm.path('pow').set('globalClasses', Object({'POWManager': manager}))
    from formats import Placement
    banner_root = next(c for f in movies[1].apt.root_frames for c in f
                       if isinstance(c, Placement) and c.name == 'Widget')
    assert banner_root.flags & 8, 'Banner needs a colour transform before its constructor'
    assert banner_root.color >> 24 == 0, 'Banner can flash on its first native frame'
    assert banner_root.bias >> 24 == 0, 'Alpha bias can reveal the native banner'
    def connection(visible=True):
        result = Object({'_visible': visible, '_alpha': (banner_root.color >> 24) * 100 / 255}, prototype=easfc)
        manager.set('m_widgetComponent', result); return result

    def header(tournament=False):
        result = Object({'m_objData': Object({'IS_TOURNAMENTMODE': str(int(tournament))}),
                         build.LOGO: Object({'_visible': True})}, prototype=career)
        vm.invoke(career.get('InitComponents'), result)
        assert result.get(build.LOGO).get('_visible') is False
        return result

    def invoke(obj, method, *args): vm.invoke(obj.get(method), obj, args)

    # Before any hub exists, between their shutdown/creation, and after a
    # native connection update: the card must never become renderable.
    def transparent(obj): assert obj.get('_alpha') == 0
    standalone = connection(); transparent(standalone)
    invoke(standalone, 'InitializeLayout'); transparent(standalone)
    invoke(standalone, 'ChangeWidgetState', 3, 2, False); transparent(standalone)
    assert vm.global_.get(build.OWNER) is None

    main_actions = movies[2]
    assert not any(isinstance(c, tuple) and c[0] == 'action'
                   for f in main_actions.apt.characters[9].frames for c in f)
    main_constructor = vm.path('game.widgets.MainHubWidget')
    def main_menu():
        result = Object({build.LOGO: Object({'_visible': True}),
                         'mcLogoAccess': Object({'txtTrial': Object()}),
                         'mcLogoNormal': Object()}, prototype=main)
        vm.invoke(main_constructor, result)
        return result

    # Both logos end at the same native card edge, despite different origins.
    for actions, cid, origin in [(movies[0], 13, (109,73)), (movies[2], 9, (122,80))]:
        placement = next(c for f in actions.apt.characters[cid].frames for c in f
                         if getattr(c, 'name', '') == build.LOGO)
        sx, _, _, sy, x, y = placement.matrix
        assert abs(origin[0] + x + 512 * sx - 1811) < .001
        assert abs(origin[1] + y - 73) < .001
        assert abs(sy * 167 - 79) < .001

    widget = connection(); home = main_menu()
    assert widget.get('_visible') is False and vm.global_.get(build.OWNER) is home
    invoke(widget, 'ChangeWidgetState', 3, 2, False); assert widget.get('_visible') is False
    widget.set('_visible', True)
    published = Object({'header': Object({'isTrial': False})})
    invoke(home, 'Publish', published, 44)
    assert ('original.Publish', (published, 44)) in calls
    assert widget.get('_visible') is False and vm.global_.get(build.OWNER) is home
    invoke(home, 'Shutdown'); assert widget.get('_visible') is True; transparent(widget)
    invoke(widget, 'ChangeWidgetState', 3, 2, False); transparent(widget)
    manager.set('m_widgetComponent', None); home = main_menu()
    assert vm.global_.get(build.OWNER) is home
    widget = connection(); invoke(widget, 'InitializeLayout')
    assert widget.get('_visible') is False
    invoke(home, 'Shutdown'); assert widget.get('_visible') is True

    widget = connection(); active = header(); invoke(active, 'SetData')
    assert widget.get('_visible') is False
    assert active.get(build.LOGO).get('_visible') is True
    assert vm.global_.get(build.OWNER) is active
    invoke(active, 'SetData')
    assert widget.get(build.PRIOR) is True  # Repeated data publishes cannot save the hidden state.
    invoke(widget, 'ChangeWidgetState', 3, 2, False)
    assert calls[-1] == ('original.ChangeWidgetState', (3, 2, False))
    assert widget.get('_visible') is False
    # New native widget loaded while the career screen remains active.
    widget = connection(); invoke(widget, 'InitializeLayout')
    assert widget.get('_visible') is False
    invoke(active, 'Shutdown')
    assert widget.get('_visible') is True and vm.global_.get(build.OWNER) is None
    transparent(widget)
    invoke(widget, 'ChangeWidgetState', 2, 1, True)
    assert widget.get('_visible') is True; transparent(widget)

    widget = connection(False); active = header(); invoke(active, 'SetData'); invoke(active, 'Shutdown')
    assert widget.get('_visible') is False  # Preserve a preexisting hidden widget.
    widget = connection(); tournament = header(True); invoke(tournament, 'SetData')
    assert widget.get('_visible') is True
    assert tournament.get(build.LOGO).get('_visible') is False
    assert vm.global_.get(build.OWNER) is None
    invoke(tournament, 'Shutdown'); assert widget.get('_visible') is True

    widget = connection(); old = header(); invoke(old, 'SetData')
    new = header(); invoke(new, 'SetData'); invoke(old, 'Shutdown')
    assert widget.get('_visible') is False and vm.global_.get(build.OWNER) is new
    invoke(new, 'Shutdown'); assert widget.get('_visible') is True

    manager.set('m_widgetComponent', None); active = header(); invoke(active, 'SetData'); invoke(active, 'Shutdown')
    assert vm.global_.get(build.OWNER) is None
    widget = connection(); home = main_menu(); active = header(); invoke(active, 'SetData')
    invoke(home, 'Publish', published, 44)
    assert vm.global_.get(build.OWNER) is active and widget.get('_visible') is False
    invoke(home, 'Shutdown'); assert widget.get('_visible') is False and vm.global_.get(build.OWNER) is active
    invoke(active, 'Shutdown'); assert widget.get('_visible') is True
    widget = connection(); active = header(); invoke(active, 'SetData'); home = main_menu()
    invoke(active, 'Shutdown'); assert widget.get('_visible') is False and vm.global_.get(build.OWNER) is home
    invoke(home, 'Shutdown'); assert widget.get('_visible') is True
    assert not vm.errors
    result = {'native_action_vm': 'passed', 'checks': [
        'career entry/repeated publishes', 'connection refresh and argument order',
        'widget recreation', 'career exit restoration', 'initially hidden widget',
        'tournament unchanged', 'overlapping header unload', 'missing widget',
        'idempotent class initialization', 'original methods invoked',
        'real main-menu constructor without timeline/data-provider publish',
        'main-menu late EASFC creation', 'main-menu connection and publish refresh',
        'late main-menu publish preserves career ownership',
        'main-menu/career overlapping transitions', 'shared right/top alignment',
        'banner transparent before its native constructor',
        'banner transparent between hub owners and after connection refresh'], 'steps': vm.steps}
    result['native_function_headers'] = 'non-null names and parameter tables verified'
    result['native_relocation_stream'] = 'no embedded End instructions in function bodies'
    result['native_global_access'] = '0x58 is a string; ownership uses the 0x71 global object'
    result['native_banner_first_paint'] = 'zero root alpha and alpha bias; opacity enforced after native updates'
    (output / 'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--studio', type=Path, default=Path('U:/fifa 16/ScoreboardStudio'))
    args = parser.parse_args(); sys.path.insert(0, str(args.studio)); verify(args.output)
