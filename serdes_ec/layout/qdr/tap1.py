# -*- coding: utf-8 -*-

"""This module defines classes needed to build the DFE tap1 summer."""

from typing import TYPE_CHECKING, Dict, Any, Set

from itertools import chain

from bag.layout.routing import TrackManager, TrackID
from bag.layout.template import TemplateBase

from .base import HybridQDRBaseInfo, HybridQDRBase
from .laygo import SinClkDivider

if TYPE_CHECKING:
    from bag.layout.template import TemplateDB


class Tap1FB(HybridQDRBase):
    """tap1 summer DFE feedback Gm and the first digital latch.

    Parameters
    ----------
    temp_db : TemplateDB
            the template database.
    lib_name : str
        the layout library name.
    params : Dict[str, Any]
        the parameter values.
    used_names : Set[str]
        a set of already used cell names.
    **kwargs
        dictionary of optional parameters.  See documentation of
        :class:`bag.layout.template.TemplateBase` for details.
    """

    def __init__(self, temp_db, lib_name, params, used_names, **kwargs):
        # type: (TemplateDB, str, Dict[str, Any], Set[str], **kwargs) -> None
        HybridQDRBase.__init__(self, temp_db, lib_name, params, used_names, **kwargs)
        self._sch_params = None
        self._fg_tot = None

    @property
    def sch_params(self):
        # type: () -> Dict[str, Any]
        return self._sch_params

    @property
    def fg_tot(self):
        # type: () -> int
        return self._fg_tot

    @classmethod
    def get_default_param_values(cls):
        # type: () -> Dict[str, Any]
        return dict(
            fg_min=0,
            show_pins=True,
            options=None,
        )

    @classmethod
    def get_params_info(cls):
        # type: () -> Dict[str, str]
        return dict(
            lch='channel length, in meters.',
            ptap_w='NMOS substrate width, in meters/number of fins.',
            ntap_w='PMOS substrate width, in meters/number of fins.',
            w_dict='NMOS/PMOS width dictionary.',
            th_dict='NMOS/PMOS threshold flavor dictionary.',
            seg_fb='number of segments dictionary for tap1 feedback.',
            seg_lat='number of segments dictionary for digital latch.',
            fg_dum='Number of single-sided edge dummy fingers.',
            fg_min='Minimum number of fingers total.',
            tr_widths='Track width dictionary.',
            tr_spaces='Track spacing dictionary.',
            show_pins='True to create pin labels.',
            options='other AnalogBase options',
        )

    def draw_layout(self):
        lch = self.params['lch']
        ptap_w = self.params['ptap_w']
        ntap_w = self.params['ntap_w']
        w_dict = self.params['w_dict']
        th_dict = self.params['th_dict']
        seg_fb = self.params['seg_fb']
        seg_lat = self.params['seg_lat']
        fg_dumr = self.params['fg_dum']
        fg_min = self.params['fg_min']
        tr_widths = self.params['tr_widths']
        tr_spaces = self.params['tr_spaces']
        show_pins = self.params['show_pins']
        options = self.params['options']

        if options is None:
            options = {}

        # get track manager and wire names
        tr_manager = TrackManager(self.grid, tr_widths, tr_spaces)
        wire_names = {
            'tail': dict(g=['clk'], ds=['ntail']),
            'nen': dict(g=['en'], ds=['ntail']),
            'in': dict(g=['in', 'in'], ds=[]),
            'pen': dict(ds=['out', 'out'], g=['en']),
            'load': dict(ds=['ptail'], g=['clk']),
        }

        # get total number of fingers
        hm_layer = self.mos_conn_layer + 1
        top_layer = vm_layer = hm_layer + 1
        qdr_info = HybridQDRBaseInfo(self.grid, lch, 0, top_layer=top_layer,
                                     end_mode=12, **options)
        fg_sep_out = qdr_info.get_fg_sep_from_hm_space(tr_manager.get_width(hm_layer, 'out'),
                                                       round_even=True)
        fg_sep_load = qdr_info.get_fg_sep_from_hm_space(tr_manager.get_width(hm_layer, 'en'),
                                                        round_even=True)
        fg_sep_load = max(0, fg_sep_load - 2)

        fb_info = qdr_info.get_integ_amp_info(seg_fb, fg_dum=0, fg_sep_load=fg_sep_load)
        latch_info = qdr_info.get_integ_amp_info(seg_lat, fg_dum=0, fg_sep_load=fg_sep_load)

        fg_latch = latch_info['fg_tot']
        fg_amp = fb_info['fg_tot'] + fg_latch + fg_sep_out
        fg_tot = max(fg_amp + 2 * fg_dumr, fg_min)
        fg_duml = fg_tot - fg_dumr - fg_amp

        self.draw_rows(lch, fg_tot, ptap_w, ntap_w, w_dict, th_dict, tr_manager,
                       wire_names, top_layer=top_layer, end_mode=12, **options)

        # draw amplifier
        lat_ports, _ = self.draw_integ_amp(fg_duml, seg_lat, fg_dum=0,
                                           fg_sep_load=fg_sep_load, net_prefix='lat_')
        fb_ports, _ = self.draw_integ_amp(fg_duml + fg_latch + fg_sep_out, seg_fb,
                                          fg_dum=0, fg_sep_load=fg_sep_load, net_prefix='fb_')

        vss_warrs, vdd_warrs = self.fill_dummy()

        w_vm_en = tr_manager.get_width(vm_layer, 'en')

        for name in ('inp', 'inn'):
            cur_warr = self.connect_wires([lat_ports[name], fb_ports[name]])
            self.add_pin(name, cur_warr, show=show_pins)

        nen = self.connect_wires([lat_ports['nen0'], fb_ports['nen0']])[0]
        en0_list = []
        for idx, warr in enumerate(chain(lat_ports['pen0'], fb_ports['pen0'])):
            mode = -1 if idx % 2 == 0 else 1
            mtr = self.grid.coord_to_nearest_track(vm_layer, warr.middle, half_track=True,
                                                   mode=mode)
            tid = TrackID(vm_layer, mtr, width=w_vm_en)
            en0_list.append(self.connect_to_tracks([warr, nen], tid))
        self.add_pin('en0', en0_list, show=show_pins)

        for name, port_name in (('pen1', 'en1'), ('clkp', 'clkp'), ('clkn', 'clkn')):
            warr_list = []
            for idx, warr in enumerate(chain(lat_ports[name], fb_ports[name])):
                mode = -1 if idx % 2 == 0 else 1
                mtr = self.grid.coord_to_nearest_track(vm_layer, warr.middle, half_track=True,
                                                       mode=mode)
                tid = TrackID(vm_layer, mtr, width=w_vm_en)
                warr_list.append(self.connect_to_tracks(warr, tid, min_len_mode=0))

            self.add_pin(port_name, warr_list, label=port_name + ':', show=show_pins)

        self.add_pin('lat_clkp', lat_ports['bias_clkp'], show=show_pins)
        self.add_pin('fb_clkp', fb_ports['bias_clkp'], show=show_pins)
        for name in ('outp', 'outn'):
            for prefix, port in (('lat_', lat_ports), ('fb_', fb_ports)):
                self.add_pin(prefix + name, port[name], show=show_pins)

        self.add_pin('VSS', vss_warrs, show=show_pins)
        self.add_pin('VDD', vdd_warrs, show=show_pins)

        # set properties
        self._sch_params = dict(
            lch=lch,
            w_dict=w_dict,
            th_dict=th_dict,
            seg_fb=seg_fb,
            seg_lat=seg_lat,
            dum_info=self.get_sch_dummy_info(),
        )
        self._fg_tot = fg_tot


class Tap1Main(HybridQDRBase):
    """The DFE tap1 summer main tap.

    Parameters
    ----------
    temp_db : TemplateDB
            the template database.
    lib_name : str
        the layout library name.
    params : Dict[str, Any]
        the parameter values.
    used_names : Set[str]
        a set of already used cell names.
    **kwargs
        dictionary of optional parameters.  See documentation of
        :class:`bag.layout.template.TemplateBase` for details.
    """

    def __init__(self, temp_db, lib_name, params, used_names, **kwargs):
        # type: (TemplateDB, str, Dict[str, Any], Set[str], **kwargs) -> None
        HybridQDRBase.__init__(self, temp_db, lib_name, params, used_names, **kwargs)
        self._sch_params = None
        self._fg_tot = None

    @property
    def sch_params(self):
        # type: () -> Dict[str, Any]
        return self._sch_params

    @property
    def fg_tot(self):
        # type: () -> int
        return self._fg_tot

    @classmethod
    def get_default_param_values(cls):
        # type: () -> Dict[str, Any]
        return dict(
            fg_min=0,
            is_end=False,
            show_pins=True,
            options=None,
        )

    @classmethod
    def get_params_info(cls):
        # type: () -> Dict[str, str]
        return dict(
            lch='channel length, in meters.',
            ptap_w='NMOS substrate width, in meters/number of fins.',
            ntap_w='PMOS substrate width, in meters/number of fins.',
            w_dict='NMOS/PMOS width dictionary.',
            th_dict='NMOS/PMOS threshold flavor dictionary.',
            seg_dict='number of segments dictionary.',
            fg_dum='Number of single-sided edge dummy fingers.',
            fg_min='Minimum number of fingers total.',
            tr_widths='Track width dictionary.',
            tr_spaces='Track spacing dictionary.',
            show_pins='True to create pin labels.',
            is_end='True if this is the end row.',
            options='other AnalogBase options',
        )

    def draw_layout(self):
        lch = self.params['lch']
        ptap_w = self.params['ptap_w']
        ntap_w = self.params['ntap_w']
        w_dict = self.params['w_dict']
        th_dict = self.params['th_dict']
        seg_dict = self.params['seg_dict']
        fg_dumr = self.params['fg_dum']
        fg_min = self.params['fg_min']
        tr_widths = self.params['tr_widths']
        tr_spaces = self.params['tr_spaces']
        show_pins = self.params['show_pins']
        is_end = self.params['is_end']
        options = self.params['options']

        end_mode = 13 if is_end else 12
        if options is None:
            options = {}

        # get track manager and wire names
        tr_manager = TrackManager(self.grid, tr_widths, tr_spaces)
        wire_names = {
            'tail': dict(g=['clk'], ds=['ntail']),
            'nen': dict(g=['en'], ds=['ntail']),
            'in': dict(g=['in', 'in'], ds=[]),
            'pen': dict(ds=['out', 'out'], g=['en']),
            'load': dict(ds=['ptail'], g=['clk']),
        }

        # get total number of fingers
        hm_layer = self.mos_conn_layer + 1
        top_layer = vm_layer = hm_layer + 1
        qdr_info = HybridQDRBaseInfo(self.grid, lch, 0, top_layer=top_layer,
                                     end_mode=end_mode, **options)
        fg_sep_load = qdr_info.get_fg_sep_from_hm_space(tr_manager.get_width(hm_layer, 'en'),
                                                        round_even=True)
        fg_sep_load = max(0, fg_sep_load - 2)

        amp_info = qdr_info.get_integ_amp_info(seg_dict, fg_dum=0, fg_sep_load=fg_sep_load)

        fg_amp = amp_info['fg_tot']
        fg_tot = max(fg_amp + 2 * fg_dumr, fg_min)
        fg_duml = fg_tot - fg_dumr - fg_amp

        self.draw_rows(lch, fg_tot, ptap_w, ntap_w, w_dict, th_dict, tr_manager,
                       wire_names, top_layer=top_layer, end_mode=end_mode, **options)

        # draw amplifier
        ports, _ = self.draw_integ_amp(fg_duml, seg_dict, fg_dum=0, fg_sep_load=fg_sep_load)

        vss_warrs, vdd_warrs = self.fill_dummy()

        w_vm_en = tr_manager.get_width(vm_layer, 'en')

        for name in ('inp', 'inn', 'outp', 'outn', 'bias_clkp'):
            self.add_pin(name, ports[name], show=show_pins)

        nen = ports['nen0']
        en0_list = []
        for idx, warr in enumerate(ports['pen1']):
            mode = -1 if idx % 2 == 0 else 1
            mtr = self.grid.coord_to_nearest_track(vm_layer, warr.middle, half_track=True,
                                                   mode=mode)
            tid = TrackID(vm_layer, mtr, width=w_vm_en)
            en0_list.append(self.connect_to_tracks([warr, nen], tid))
        self.add_pin('en0', en0_list, show=show_pins)

        for name, port_name in (('pen0', 'en1'), ('clkp', 'clkn'), ('clkn', 'clkp')):
            warr_list = []
            for idx, warr in enumerate(ports[name]):
                mode = -1 if idx % 2 == 0 else 1
                mtr = self.grid.coord_to_nearest_track(vm_layer, warr.middle, half_track=True,
                                                       mode=mode)
                tid = TrackID(vm_layer, mtr, width=w_vm_en)
                warr_list.append(self.connect_to_tracks(warr, tid, min_len_mode=0))

            self.add_pin(port_name, warr_list, label=port_name + ':', show=show_pins)

        self.add_pin('VSS', vss_warrs, show=show_pins)
        self.add_pin('VDD', vdd_warrs, show=show_pins)

        # set schematic parameters
        self._sch_params = dict(
            lch=lch,
            w_dict=w_dict,
            th_dict=th_dict,
            seg_dict=seg_dict,
            dum_info=self.get_sch_dummy_info(),
        )
        self._fg_tot = fg_tot


class Tap1MainRow(TemplateBase):
    """The DFE tap1 summer main tap and clock divider.

    Parameters
    ----------
    temp_db : TemplateDB
            the template database.
    lib_name : str
        the layout library name.
    params : Dict[str, Any]
        the parameter values.
    used_names : Set[str]
        a set of already used cell names.
    **kwargs
        dictionary of optional parameters.  See documentation of
        :class:`bag.layout.template.TemplateBase` for details.
    """

    def __init__(self, temp_db, lib_name, params, used_names, **kwargs):
        # type: (TemplateDB, str, Dict[str, Any], Set[str], **kwargs) -> None
        TemplateBase.__init__(self, temp_db, lib_name, params, used_names, **kwargs)
        self._sch_params = None
        self._fg_tot = None

    @property
    def sch_params(self):
        # type: () -> Dict[str, Any]
        return self._sch_params

    @classmethod
    def get_default_param_values(cls):
        # type: () -> Dict[str, Any]
        return dict(
            fg_min=0,
            is_end=False,
            show_pins=True,
            options=None,
        )

    @classmethod
    def get_params_info(cls):
        # type: () -> Dict[str, str]
        return dict(
            config='Laygo configuration dictionary for the divider.',
            lch='channel length, in meters.',
            ptap_w='NMOS substrate width, in meters/number of fins.',
            ntap_w='PMOS substrate width, in meters/number of fins.',
            w_dict='NMOS/PMOS width dictionary.',
            th_dict='NMOS/PMOS threshold flavor dictionary.',
            seg_main='number of segments dictionary for main tap.',
            seg_div='number of segments dictionary for clock divider.',
            fg_dum='Number of single-sided edge dummy fingers.',
            tr_widths='Track width dictionary.',
            tr_spaces='Track spacing dictionary.',
            fg_min='Minimum number of fingers total.',
            is_end='True if this is the end row.',
            show_pins='True to create pin labels.',
            options='other AnalogBase options',
        )

    def draw_layout(self):
        # get parameters
        config = self.params['config']
        seg_div = self.params['seg_div']
        show_pins = self.params['show_pins']
        tr_widths = self.params['tr_widths']
        tr_spaces = self.params['tr_spaces']
        fg_min = self.params['fg_min']

        # get layout masters
        main_params = self.params.copy()
        main_params['show_pins'] = False
        del main_params['config']
        del main_params['seg_div']
        main_params['seg_dict'] = main_params['seg_main']
        del main_params['seg_main']
        del main_params['fg_min']

        m_master = self.new_template(params=main_params, temp_cls=Tap1Main)

        div_params = dict(
            config=config,
            row_layout_info=m_master.row_layout_info,
            seg_dict=seg_div,
            tr_widths=tr_widths,
            tr_spaces=tr_spaces,
            show_pins=False,
        )
        d_master = self.new_template(params=div_params, temp_cls=SinClkDivider)

        # place instances
        top_layer = m_master.top_layer
        d_inst = self.add_instance(d_master, 'XDIV', loc=(0, 0))
        m_inst = self.add_instance(m_master, 'XMAIN', loc=(d_master.bound_box.right_unit, 0),
                                   unit_mode=True)

        self.add_rect('M7', d_inst.array_box)
        self.add_rect('M8', m_inst.array_box)


class Tap1Summer(TemplateBase):
    """An integrating amplifier.

    Parameters
    ----------
    temp_db : TemplateDB
            the template database.
    lib_name : str
        the layout library name.
    params : Dict[str, Any]
        the parameter values.
    used_names : Set[str]
        a set of already used cell names.
    **kwargs
        dictionary of optional parameters.  See documentation of
        :class:`bag.layout.template.TemplateBase` for details.
    """

    def __init__(self, temp_db, lib_name, params, used_names, **kwargs):
        # type: (TemplateDB, str, Dict[str, Any], Set[str], **kwargs) -> None
        TemplateBase.__init__(self, temp_db, lib_name, params, used_names, **kwargs)
        self._sch_params = None

    @property
    def sch_params(self):
        # type: () -> Dict[str, Any]
        return self._sch_params

    @classmethod
    def get_default_param_values(cls):
        # type: () -> Dict[str, Any]
        return dict(
            is_end=False,
            show_pins=True,
            options=None,
        )

    @classmethod
    def get_params_info(cls):
        # type: () -> Dict[str, str]
        return dict(
            lch='channel length, in meters.',
            ptap_w='NMOS substrate width, in meters/number of fins.',
            ntap_w='PMOS substrate width, in meters/number of fins.',
            w_dict='NMOS/PMOS width dictionary.',
            th_dict='NMOS/PMOS threshold flavor dictionary.',
            seg_main='number of segments dictionary for main tap.',
            seg_fb='number of segments dictionary for tap1 feedback.',
            seg_lat='number of segments dictionary for digital latch.',
            fg_dum='Number of single-sided edge dummy fingers.',
            tr_widths='Track width dictionary.',
            tr_spaces='Track spacing dictionary.',
            show_pins='True to create pin labels.',
            is_end='True if this is the end row.',
            options='other AnalogBase options',
        )

    def draw_layout(self):
        # get parameters
        show_pins = self.params['show_pins']
        tr_widths = self.params['tr_widths']
        tr_spaces = self.params['tr_spaces']

        tr_manager = TrackManager(self.grid, tr_widths, tr_spaces)

        fb_params = self.params.copy()
        fb_params['show_pins'] = False
        del fb_params['seg_main']
        del fb_params['is_end']
        main_params = self.params.copy()
        main_params['show_pins'] = False
        del main_params['seg_fb']
        del main_params['seg_lat']
        main_params['seg_dict'] = main_params['seg_main']
        del main_params['seg_main']

        # get masters
        f_master = self.new_template(params=fb_params, temp_cls=Tap1FB)
        m_master = self.new_template(params=main_params, temp_cls=Tap1Main)
        fg_min = max(f_master.fg_tot, m_master.fg_tot)
        if f_master.fg_tot < fg_min:
            f_master = f_master.new_template_with(fg_min=fg_min)
        if m_master.fg_tot < fg_min:
            m_master = m_master.new_template_with(fg_min=fg_min)

        # place instances
        top_layer = m_master.top_layer + 1
        _, blk_h = self.grid.get_block_size(top_layer, unit_mode=True, half_blk_y=False)
        h_blk = m_master.array_box.height_unit + f_master.array_box.height_unit
        h_tot = -(-h_blk // blk_h) * blk_h
        h_mid = h_tot // 2
        y0 = h_mid - m_master.array_box.height_unit
        y1 = y0 + h_blk
        m_inst = self.add_instance(m_master, 'XMAIN', loc=(0, y0), unit_mode=True)
        f_inst = self.add_instance(f_master, 'XFB', loc=(0, y1), orient='MX', unit_mode=True)

        # set size
        self.array_box = m_inst.array_box.merge(f_inst.array_box)
        self.set_size_from_array_box(top_layer)

        # export pins in-place
        exp_list = [(m_inst, 'outp', 'm_outp', True), (m_inst, 'outn', 'm_outn', True),
                    (m_inst, 'inp', 'inp', False), (m_inst, 'inn', 'inn', False),
                    (m_inst, 'bias_clkp', 'm_clkp', False), (f_inst, 'inp', 'm_outp', True),
                    (f_inst, 'inn', 'm_outn', True), (f_inst, 'fb_clkp', 'f_clkp', False),
                    (f_inst, 'lat_clkp', 'd_clkp', False), (f_inst, 'fb_outp', 'f_outp', False),
                    (f_inst, 'fb_outn', 'f_outn', False), (f_inst, 'lat_outp', 'd_outp', False),
                    (f_inst, 'lat_outn', 'd_outn', False),
                    ]
        for inst, port, name, vconn in exp_list:
            label = name + ':' if vconn else name
            self.reexport(inst.get_port(port), net_name=name, label=label, show=show_pins)

        # compute VDD/PMOS clks and enables placement
        _, wire_locs = tr_manager.place_wires(top_layer, ['en', 'clk', 'sup', 'clk', 'en'])
        vdd_tidx = self.grid.coord_to_track(top_layer, h_mid, unit_mode=True)
        tr_off = vdd_tidx - wire_locs[2]

        # connect PMOS clocks
        hm_w_clk = tr_manager.get_width(top_layer, 'clk')
        clkp_tidx = wire_locs[1] + tr_off
        clkn_tidx = wire_locs[3] + tr_off
        clkp_warrs = m_inst.get_all_port_pins('clkp')
        clkn_warrs = m_inst.get_all_port_pins('clkn')
        clkp_warrs.extend(f_inst.get_all_port_pins('clkn'))
        clkn_warrs.extend(f_inst.get_all_port_pins('clkp'))

        clkp, clkn = self.connect_differential_tracks(clkp_warrs, clkn_warrs, top_layer,
                                                      clkp_tidx, clkn_tidx, width=hm_w_clk)
        self.add_pin('clkp', clkp, show=show_pins)
        self.add_pin('clkn', clkn, show=show_pins)

        # connect PMOS enables
        hm_w_en = tr_manager.get_width(top_layer, 'en')
        en1_warrs = m_inst.get_all_port_pins('en1')
        en1_tidx = self.grid.coord_to_nearest_track(top_layer, en1_warrs[0].middle,
                                                    half_track=True, mode=1)
        en1_tidx = min(wire_locs[0] + tr_off, en1_tidx)
        en1_tid = TrackID(top_layer, en1_tidx, width=hm_w_en)
        self.add_pin('m_en1', self.connect_to_tracks(en1_warrs, en1_tid), show=show_pins)
        en2_warrs = f_inst.get_all_port_pins('en1')
        en2_tidx = clkn_tidx + (clkp_tidx - en1_tidx)
        en2_tid = TrackID(top_layer, en2_tidx, width=hm_w_en)
        self.add_pin('f_en2', self.connect_to_tracks(en2_warrs, en2_tid), show=show_pins)

        # connect VDD
        m_vdd = m_inst.get_all_port_pins('VDD')[0]
        f_vdd = f_inst.get_all_port_pins('VDD')[0]
        hm_w_vdd = tr_manager.get_width(top_layer, 'sup')
        vdd = self.add_wires(top_layer, vdd_tidx, m_vdd.lower, m_vdd.upper, width=hm_w_vdd)
        for warr in (m_vdd, f_vdd, vdd):
            self.add_pin('VDD', warr, show=show_pins)