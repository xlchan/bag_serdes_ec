# -*- coding: utf-8 -*-

"""This module defines classes needed to build the Hybrid-QDR FFE/DFE summer."""

from typing import TYPE_CHECKING, Dict, Any, Set

from itertools import chain

from bag.layout.template import TemplateBase
from bag.layout.routing.base import TrackManager, TrackID

from ..laygo.misc import LaygoDummy
from ..laygo.divider import SinClkDivider
from .amp import IntegAmp

if TYPE_CHECKING:
    from bag.layout.template import TemplateDB


class TapXSummerCell(TemplateBase):
    """A summer cell containing a single DFE/FFE tap with the corresponding latch.

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
        self._lat_row_layout_info = None
        self._lat_track_info = None
        self._amp_masters = None
        self._sd_pitch = None

    @property
    def sch_params(self):
        # type: () -> Dict[str, Any]
        return self._sch_params

    @property
    def lat_row_layout_info(self):
        # type: () -> Dict[str, Any]
        return self._lat_row_layout_info

    @property
    def lat_track_info(self):
        # type: () -> Dict[str, Any]
        return self._lat_track_info

    @property
    def sd_pitch(self):
        # type: () -> int
        return self._sd_pitch

    def get_vm_coord(self, vm_width, is_left, is_out):
        # type: (int, bool, bool) -> int
        if is_out:
            top_coord = self._amp_masters[1].get_vm_coord(vm_width, is_left, 1)
            bot_coord = self._amp_masters[0].get_vm_coord(vm_width, is_left, 0)
        else:
            top_coord = self._amp_masters[1].get_vm_coord(vm_width, is_left, 2)
            bot_coord = self._amp_masters[0].get_vm_coord(vm_width, is_left, 1)

        if is_left:
            return min(top_coord, bot_coord)
        return max(top_coord, bot_coord)

    @classmethod
    def get_default_param_values(cls):
        # type: () -> Dict[str, Any]
        return dict(
            flip_sign=False,
            end_mode=12,
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
            w_sum='NMOS/PMOS width dictionary for summer.',
            w_lat='NMOS/PMOS width dictionary for latch.',
            th_sum='NMOS/PMOS threshold flavor dictionary.',
            th_lat='NMOS/PMOS threshold dictoary for latch.',
            seg_sum='number of segments dictionary for summer tap.',
            seg_lat='number of segments dictionary for latch.',
            fg_duml='Number of left edge dummy fingers.',
            fg_dumr='Number of right edge dummy fingers.',
            tr_widths='Track width dictionary.',
            tr_spaces='Track spacing dictionary.',
            flip_sign='True to flip summer output sign.',
            end_mode='The AnalogBase end_mode flag.',
            show_pins='True to create pin labels.',
            options='other AnalogBase options',
        )

    def draw_layout(self):
        # get parameters
        fg_duml = self.params['fg_duml']
        fg_dumr = self.params['fg_dumr']
        flip_sign = self.params['flip_sign']
        end_mode = self.params['end_mode']
        show_pins = self.params['show_pins']

        # get layout parameters
        sum_params = dict(
            w_dict=self.params['w_sum'],
            th_dict=self.params['th_sum'],
            seg_dict=self.params['seg_sum'],
            top_layer=None,
            flip_sign=flip_sign,
            but_sw=True,
            show_pins=False,
            end_mode=end_mode,
        )
        lat_params = dict(
            w_dict=self.params['w_lat'],
            th_dict=self.params['th_lat'],
            seg_dict=self.params['seg_lat'],
            top_layer=None,
            flip_sign=False,
            but_sw=False,
            show_pins=False,
            end_mode=end_mode & 0b1100,
        )
        for key in ('lch', 'ptap_w', 'ntap_w', 'fg_duml', 'fg_dumr', 'tr_widths',
                    'tr_spaces', 'options'):
            sum_params[key] = lat_params[key] = self.params[key]

        # get masters
        l_master = self.new_template(params=lat_params, temp_cls=IntegAmp)
        s_master = self.new_template(params=sum_params, temp_cls=IntegAmp)
        if l_master.fg_tot < s_master.fg_tot:
            # update latch master
            fg_inc = s_master.fg_tot - l_master.fg_tot
            fg_inc2 = fg_inc // 2
            fg_duml2 = fg_duml + fg_inc2
            fg_dumr2 = fg_dumr + fg_inc - fg_inc2
            l_master = l_master.new_template_with(fg_duml=fg_duml2, fg_dumr=fg_dumr2)
        elif s_master.fg_tot < l_master.fg_tot:
            fg_inc = l_master.fg_tot - s_master.fg_tot
            fg_inc2 = fg_inc // 2
            fg_duml2 = fg_duml + fg_inc2
            fg_dumr2 = fg_dumr + fg_inc - fg_inc2
            s_master = s_master.new_template_with(fg_duml=fg_duml2, fg_dumr=fg_dumr2)

        # place instances
        s_inst = self.add_instance(s_master, 'XSUM', loc=(0, 0), unit_mode=True)
        y0 = s_inst.array_box.top_unit + l_master.array_box.top_unit
        d_inst = self.add_instance(l_master, 'XLAT', loc=(0, y0), orient='MX', unit_mode=True)

        # set size
        self.array_box = s_inst.array_box.merge(d_inst.array_box)
        self.set_size_from_bound_box(s_master.top_layer, s_inst.bound_box.merge(d_inst.bound_box))

        # export pins in-place
        exp_list = [(s_inst, 'clkp', 'clkn', True), (s_inst, 'clkn', 'clkp', True),
                    (s_inst, 'casc', 'casc', False),
                    (s_inst, 'casc<1>', 'casc<1>', False), (s_inst, 'casc<0>', 'casc<0>', False),
                    (s_inst, 'inp', 'outp_l', True), (s_inst, 'inn', 'outn_l', True),
                    (s_inst, 'biasp', 'biasn_s', False),
                    (s_inst, 'en<3>', 'en<2>', True), (s_inst, 'en<2>', 'en<1>', False),
                    (s_inst, 'setp', 'setp', False), (s_inst, 'setn', 'setn', False),
                    (s_inst, 'pulse', 'pulse', False),
                    (s_inst, 'outp', 'outp_s', False), (s_inst, 'outn', 'outn_s', False),
                    (s_inst, 'VDD', 'VDD', True), (s_inst, 'VSS', 'VSS', True),
                    (d_inst, 'clkp', 'clkp', True), (d_inst, 'clkn', 'clkn', True),
                    (d_inst, 'inp', 'inp', False), (d_inst, 'inn', 'inn', False),
                    (d_inst, 'biasp', 'biasp_l', False),
                    (d_inst, 'en<3>', 'en<3>', True), (d_inst, 'en<2>', 'en<2>', True),
                    (d_inst, 'setp', 'setp', False), (d_inst, 'setn', 'setn', False),
                    (d_inst, 'pulse', 'pulse', False),
                    (d_inst, 'outp', 'outp_l', True), (d_inst, 'outn', 'outn_l', True),
                    (d_inst, 'VDD', 'VDD', True), (d_inst, 'VSS', 'VSS', True),
                    ]

        for inst, port_name, name, vconn in exp_list:
            if inst.has_port(port_name):
                port = inst.get_port(port_name)
                label = name + ':' if vconn else name
                self.reexport(port, net_name=name, label=label, show=show_pins)

        # set schematic parameters
        self._sch_params = dict(
            sum_params=s_master.sch_params,
            lat_params=l_master.sch_params,
        )
        self._lat_row_layout_info = l_master.row_layout_info
        self._lat_track_info = l_master.track_info
        self._amp_masters = s_master, l_master
        self._sd_pitch = s_master.sd_pitch_unit


class TapXSummerLast(TemplateBase):
    """A summer cell containing DFE tap2 gm cell with divider/pulse gen/dummies.

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
        self._fg_core = None
        self._amp_master = None

    @property
    def sch_params(self):
        # type: () -> Dict[str, Any]
        return self._sch_params

    @property
    def fg_core(self):
        # type: () -> int
        return self._fg_core

    def get_vm_coord(self, vm_width):
        # type: (int) -> int
        return self._amp_master.get_vm_coord(vm_width, False, 0)

    @classmethod
    def get_default_param_values(cls):
        # type: () -> Dict[str, Any]
        return dict(
            div_pos_edge=True,
            flip_sign=False,
            fg_min=0,
            end_mode=12,
            show_pins=True,
            options=None,
        )

    @classmethod
    def get_params_info(cls):
        # type: () -> Dict[str, str]
        return dict(
            config='Laygo configuration dictionary for the divider.',
            row_layout_info='The AnalogBase layout information dictionary for divider.',
            lch='channel length, in meters.',
            ptap_w='NMOS substrate width, in meters/number of fins.',
            ntap_w='PMOS substrate width, in meters/number of fins.',
            w_sum='NMOS/PMOS width dictionary for summer.',
            th_sum='NMOS/PMOS threshold flavor dictionary.',
            seg_sum='number of segments dictionary for summer tap.',
            seg_div='number of segments dictionary for clock divider.',
            seg_pul='number of segments dictionary for pulse generation.',
            fg_duml='Number of left edge dummy fingers.',
            fg_dumr='Number of right edge dummy fingers.',
            tr_widths='Track width dictionary.',
            tr_spaces='Track spacing dictionary.',
            lat_tr_info='latch output track information dictionary.',
            div_pos_edge='True if the divider triggers off positive edge of the clock.',
            flip_sign='True to flip summer output sign.',
            fg_min='Minimum number of core fingers.',
            end_mode='The AnalogBase end_mode flag.',
            show_pins='True to create pin labels.',
            options='other AnalogBase options',
        )

    def draw_layout(self):
        # get parameters
        row_layout_info = self.params['row_layout_info']
        seg_div = self.params['seg_div']
        seg_pul = self.params['seg_pul']
        fg_duml = self.params['fg_duml']
        fg_dumr = self.params['fg_dumr']
        lat_tr_info = self.params['lat_tr_info']
        div_pos_edge = self.params['div_pos_edge']
        flip_sign = self.params['flip_sign']
        fg_min = self.params['fg_min']
        end_mode = self.params['end_mode']
        show_pins = self.params['show_pins']

        no_dig = (seg_div is None and seg_pul is None)

        # get layout parameters
        sum_params = dict(
            w_dict=self.params['w_sum'],
            th_dict=self.params['th_sum'],
            seg_dict=self.params['seg_sum'],
            top_layer=None,
            flip_sign=flip_sign,
            but_sw=True,
            show_pins=False,
            end_mode=end_mode,
        )
        for key in ('lch', 'ptap_w', 'ntap_w', 'fg_duml', 'fg_dumr',
                    'tr_widths', 'tr_spaces', 'options'):
            sum_params[key] = self.params[key]

        s_master = self.new_template(params=sum_params, temp_cls=IntegAmp)
        fg_core = s_master.layout_info.fg_core
        fg_min = max(fg_min, fg_core)

        dig_params = dict(
            config=self.params['config'],
            row_layout_info=row_layout_info,
            tr_widths=self.params['tr_widths'],
            tr_spaces=self.params['tr_spaces'],
            end_mode=end_mode & 0b1100,
            show_pins=False,
        )
        if no_dig:
            # no digital block, draw LaygoDummy
            if fg_core < fg_min:
                fg_inc = fg_min - fg_core
                fg_inc2 = fg_inc // 2
                fg_duml2 = fg_duml + fg_inc2
                fg_dumr2 = fg_dumr + fg_inc - fg_inc2
                s_master = s_master.new_template_with(fg_duml=fg_duml2, fg_dumr=fg_dumr2)

            tr_info = dict(
                VDD=lat_tr_info['VDD'],
                VSS=lat_tr_info['VSS'],
            )
            dig_params['num_col'] = s_master.fg_tot
            dig_params['tr_info'] = tr_info
            d_master = self.new_template(params=dig_params, temp_cls=LaygoDummy)
            div_sch_params = pul_sch_params = None
        else:
            # draw divider
            tr_info = dict(
                VDD=lat_tr_info['VDD'],
                VSS=lat_tr_info['VSS'],
                q=lat_tr_info['outp'],
                qb=lat_tr_info['outn'],
                en=lat_tr_info['nen3'],
                clk=lat_tr_info['clkp'] if div_pos_edge else lat_tr_info['clkn'],
            )
            dig_params['seg_dict'] = seg_div
            dig_params['tr_info'] = tr_info
            dig_params['fg_min'] = fg_min
            d_master = self.new_template(params=dig_params, temp_cls=SinClkDivider)
            div_sch_params = d_master.sch_params
            pul_sch_params = None
            fg_min = max(fg_min, d_master.laygo_info.core_col)

            if fg_core < fg_min:
                fg_inc = fg_min - fg_core
                fg_inc2 = fg_inc // 2
                fg_duml2 = fg_duml + fg_inc2
                fg_dumr2 = fg_dumr + fg_inc - fg_inc2
                s_master = s_master.new_template_with(fg_duml=fg_duml2, fg_dumr=fg_dumr2)

        # TODO: add pulse generator logic here

        # place instances
        s_inst = self.add_instance(s_master, 'XSUM', loc=(0, 0), unit_mode=True)
        y0 = s_inst.array_box.top_unit + d_master.array_box.top_unit
        d_inst = self.add_instance(d_master, 'XDIG', loc=(0, y0), orient='MX', unit_mode=True)

        # set size
        self.array_box = s_inst.array_box.merge(d_inst.array_box)
        self.set_size_from_bound_box(s_master.top_layer, s_inst.bound_box.merge(d_inst.bound_box))

        # get pins
        vconn_clkp = vconn_clkn = False
        # export digital pins
        self.reexport(d_inst.get_port('VDD'), label='VDD:', show=show_pins)
        self.reexport(d_inst.get_port('VSS'), label='VSS:', show=show_pins)
        if seg_div is not None:
            # perform connections for divider
            if div_pos_edge:
                clk_name = 'clkp'
                vconn_clkp = True
            else:
                clk_name = 'clkn'
                vconn_clkn = True

            # re-export divider pins
            self.reexport(d_inst.get_port('clk'), net_name=clk_name, label=clk_name + ':',
                          show=show_pins)
            self.reexport(d_inst.get_port('q'), net_name='div', show=show_pins)
            self.reexport(d_inst.get_port('qb'), net_name='divb', show=show_pins)
            self.reexport(d_inst.get_port('en'), net_name='en_div', show=show_pins)
            self.reexport(d_inst.get_port('scan_s'), net_name='scan_div', show=show_pins)
        if seg_pul is not None:
            # TODO: perform connections for pulse generation
            pass

        # export pins in-place
        exp_list = [(s_inst, 'clkp', 'clkn', vconn_clkn), (s_inst, 'clkn', 'clkp', vconn_clkp),
                    (s_inst, 'inp', 'inp', False), (s_inst, 'inn', 'inn', False),
                    (s_inst, 'biasp', 'biasn', False),
                    (s_inst, 'casc<1>', 'casc<1>', False), (s_inst, 'casc<0>', 'casc<0>', False),
                    (s_inst, 'en<3>', 'en<2>', True), (s_inst, 'en<2>', 'en<1>', False),
                    (s_inst, 'setp', 'setp', False), (s_inst, 'setn', 'setn', False),
                    (s_inst, 'pulse', 'pulse_in', False),
                    (s_inst, 'outp', 'outp', False), (s_inst, 'outn', 'outn', False),
                    (s_inst, 'VDD', 'VDD', True), (s_inst, 'VSS', 'VSS', True),
                    ]

        for inst, port_name, name, vconn in exp_list:
            if inst.has_port(port_name):
                port = inst.get_port(port_name)
                label = name + ':' if vconn else name
                self.reexport(port, net_name=name, label=label, show=show_pins)

        # set schematic parameters
        self._sch_params = dict(
            div_pos_edge=div_pos_edge,
            sum_params=s_master.sch_params,
            div_params=div_sch_params,
            pul_params=pul_sch_params,
        )
        self._fg_core = s_master.layout_info.fg_core
        self._amp_master = s_master


class TapXSummerNoLast(TemplateBase):
    """The DFE tapx summer, without the last block.

    This is a helper class to reuse more layouts.

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
        self._ffe_track_info = None
        self._dfe_track_info = None
        self._analog_master = None

    @property
    def sch_params(self):
        # type: () -> Dict[str, Any]
        return self._sch_params

    @property
    def ffe_track_info(self):
        return self._ffe_track_info

    @property
    def dfe_track_info(self):
        return self._dfe_track_info

    @property
    def analog_master(self):
        return self._analog_master

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
            w_sum='NMOS/PMOS width dictionary for summer.',
            w_lat='NMOS/PMOS width dictionary for latch.',
            th_sum='NMOS/PMOS threshold flavor dictionary.',
            th_lat='NMOS/PMOS threshold dictoary for latch.',
            seg_sum_list='list of segment dictionaries for summer taps.',
            seg_ffe_list='list of segment dictionaries for FFE latches.',
            seg_dfe_list='list of segment dictionaries for DFE latches.',
            flip_sign_list='list of flip_sign values for summer taps.',
            fg_dum='Number of single-sided edge dummy fingers.',
            tr_widths='Track width dictionary.',
            tr_spaces='Track spacing dictionary.',
            is_end='True if this is the end row.',
            show_pins='True to create pin labels.',
            options='other AnalogBase options',
        )

    def draw_layout(self):
        # get parameters
        lch = self.params['lch']
        ptap_w = self.params['ptap_w']
        ntap_w = self.params['ntap_w']
        w_sum = self.params['w_sum']
        w_lat = self.params['w_lat']
        th_sum = self.params['th_sum']
        th_lat = self.params['th_lat']
        seg_sum_list = self.params['seg_sum_list']
        seg_ffe_list = self.params['seg_ffe_list']
        seg_dfe_list = self.params['seg_dfe_list']
        flip_sign_list = self.params['flip_sign_list']
        fg_dum = self.params['fg_dum']
        tr_widths = self.params['tr_widths']
        tr_spaces = self.params['tr_spaces']
        is_end = self.params['is_end']
        show_pins = self.params['show_pins']
        options = self.params['options']

        num_sum = len(seg_sum_list)
        num_ffe = len(seg_ffe_list)
        num_dfe = len(seg_dfe_list) + 1
        if num_sum != num_ffe + num_dfe or num_sum != len(flip_sign_list):
            raise ValueError('segment dictionary list length mismatch.')
        if num_ffe < 1:
            raise ValueError('Must have at least one FFE (last FFE is main tap).')
        if num_dfe < 2:
            # TODO: restriction exists because otherwise we do not have routing space for
            # TODO: biasp_d and biasn_d.  Remove restriction in the future?
            raise ValueError('Must have at least two DFE.')
        end_mode = 1 if is_end else 0

        # create layout masters and place instances
        tr_manager = TrackManager(self.grid, tr_widths, tr_spaces, half_space=True)
        hm_layer = IntegAmp.get_mos_conn_layer(self.grid.tech_info) + 1
        vm_layer = hm_layer + 1
        route_types = [1, 'out', 'out', 1, 'out', 'out', 1, 'out', 'out', 1]
        _, route_locs = tr_manager.place_wires(vm_layer, route_types)

        vdd_list, vss_list = [], []
        base_params = dict(lch=lch, ptap_w=ptap_w, ntap_w=ntap_w, w_sum=w_sum, w_lat=w_lat,
                           th_sum=th_sum, th_lat=th_lat, fg_duml=fg_dum, fg_dumr=fg_dum,
                           tr_widths=tr_widths, tr_spaces=tr_spaces, end_mode=end_mode,
                           show_pins=False, options=options, )
        place_info = None, None, None, 0, None
        ffe_sig_list = self._get_ffe_signals(num_ffe)
        tmp = self._create_and_place(tr_manager, num_ffe, seg_ffe_list, seg_sum_list,
                                     flip_sign_list, ffe_sig_list, end_mode, base_params, vm_layer,
                                     route_locs, place_info, vdd_list, vss_list, 'a', sig_off=0,
                                     sum_off=0, is_end=True, left_out=True)
        ffe_masters, self._ffe_track_info, ffe_sch_params, ffe_insts, place_info = tmp

        dfe_sig_list = self._get_dfe_signals(num_dfe)
        tmp = self._create_and_place(tr_manager, num_dfe - 1, seg_dfe_list, seg_sum_list,
                                     flip_sign_list, dfe_sig_list, end_mode, base_params, vm_layer,
                                     route_locs, place_info, vdd_list, vss_list, 'd', sig_off=3,
                                     sum_off=num_ffe + 1, is_end=False, left_out=False)
        dfe_masters, self._dfe_track_info, dfe_sch_params, dfe_insts, place_info = tmp

        # set size
        inst_first = ffe_insts[-1]
        inst_last = dfe_insts[0]
        self.array_box = inst_last.array_box.merge(inst_first.array_box)
        self.set_size_from_bound_box(hm_layer, inst_first.bound_box.merge(inst_last.bound_box))

        # add pins
        # connect supplies
        vdd_list = self.connect_wires(vdd_list)
        vss_list = self.connect_wires(vss_list)
        self.add_pin('VDD', vdd_list, label='VDD:', show=show_pins)
        self.add_pin('VSS', vss_list, label='VSS:', show=show_pins)

        # export/collect FFE pins
        biasm_list, biasa_list, clkp_list, clkn_list = [], [], [], []
        outs_warrs = [[], []]
        en_warrs = [[], [], [], []]
        for fidx, inst in enumerate(ffe_insts):
            if inst.has_port('casc'):
                self.reexport(inst.get_port('casc'), net_name='casc<%d>' % fidx, show=show_pins)
            biasm_list.append(inst.get_pin('biasn_s'))
            self.reexport(inst.get_port('inp'), net_name='inp_a<%d>' % fidx, show=show_pins)
            self.reexport(inst.get_port('inn'), net_name='inn_a<%d>' % fidx, show=show_pins)
            biasa_list.append(inst.get_pin('biasp_l'))
            clkp_list.extend(inst.port_pins_iter('clkp'))
            clkn_list.extend(inst.port_pins_iter('clkn'))
            en_warrs[3].extend(inst.port_pins_iter('en<3>'))
            en_warrs[2].extend(inst.port_pins_iter('en<2>'))
            if inst.has_port('en<1>'):
                en_warrs[1].extend(inst.port_pins_iter('en<1>'))
            # TODO: handle setp/setn/pulse pins
            outs_warrs[0].append(inst.get_pin('outp_s'))
            outs_warrs[1].append(inst.get_pin('outn_s'))
            self.reexport(inst.get_port('outp_l'), net_name='outp_a<%d>' % fidx,
                          label='outp_a<%d>:' % fidx, show=show_pins)
            self.reexport(inst.get_port('outn_l'), net_name='outn_a<%d>' % fidx,
                          label='outn_a<%d>:' % fidx, show=show_pins)

        # export/collect DFE pins
        biasd_list = []
        for idx, inst in enumerate(dfe_insts):
            didx = idx + 3
            self.reexport(inst.get_port('biasn_s'), net_name='biasn_s<%d>' % didx,
                          show=show_pins)
            self.reexport(inst.get_port('inp'), net_name='inp_d<%d>' % didx, show=show_pins)
            self.reexport(inst.get_port('inn'), net_name='inn_d<%d>' % didx, show=show_pins)
            biasd_list.append(inst.get_pin('biasp_l'))
            clkp_list.extend(inst.port_pins_iter('clkp'))
            clkn_list.extend(inst.port_pins_iter('clkn'))
            en_warrs[3].extend(inst.port_pins_iter('en<3>'))
            en_warrs[2].extend(inst.port_pins_iter('en<2>'))
            if inst.has_port('en<1>'):
                en_warrs[1].extend(inst.port_pins_iter('en1>'))
            if inst.has_port('casc<0>'):
                self.reexport(inst.get_port('casc<0>'), net_name='sgnp<%d>' % didx, show=show_pins)
                self.reexport(inst.get_port('casc<1>'), net_name='sgnn<%d>' % didx, show=show_pins)
            # TODO: handle setp/setn/pulse pins
            outs_warrs[0].append(inst.get_pin('outp_s'))
            outs_warrs[1].append(inst.get_pin('outn_s'))
            self.reexport(inst.get_port('outp_l'), net_name='outp_d<%d>' % didx,
                          label='outp_d<%d>:' % didx, show=show_pins)
            self.reexport(inst.get_port('outn_l'), net_name='outn_d<%d>' % didx,
                          label='outn_d<%d>:' % didx, show=show_pins)

        # connect wires and add pins
        biasm = self.connect_wires(biasm_list)
        biasa = self.connect_wires(biasa_list)
        biasd = self.connect_wires(biasd_list)
        outsp = self.connect_wires(outs_warrs[0])
        outsn = self.connect_wires(outs_warrs[1])
        lower, upper = None, None
        for warr in chain(clkp_list, clkn_list):
            if lower is None:
                lower = warr.lower_unit
                upper = warr.upper_unit
            else:
                lower = min(lower, warr.lower_unit)
                upper = max(upper, warr.upper_unit)
        clkp = self.connect_wires(clkp_list, lower=lower, upper=upper, unit_mode=True)
        clkn = self.connect_wires(clkn_list, lower=lower, upper=upper, unit_mode=True)
        self.add_pin('biasn_m', biasm, show=show_pins)
        self.add_pin('biasp_a', biasa, show=show_pins)
        self.add_pin('biasp_d', biasd, show=show_pins)
        self.add_pin('clkp', clkp, label='clkp:', show=show_pins)
        self.add_pin('clkn', clkn, label='clkn:', show=show_pins)
        self.add_pin('outp_s', outsp, show=show_pins)
        self.add_pin('outn_s', outsn, show=show_pins)

        for idx, en_warr in enumerate(en_warrs):
            if en_warr:
                en_warr = self.connect_wires(en_warr)
                name = 'en<%d>' % idx
                self.add_pin(name, en_warr, label=name + ':', show=show_pins)

        self._sch_params = dict(
            ffe_params_list=ffe_sch_params,
            dfe_params_list=dfe_sch_params,
        )
        self._analog_master = ffe_masters[0]

    @classmethod
    def _get_ffe_signals(cls, num_ffe):
        if num_ffe == 1:
            return [([1, 'out', 'out', 1, 1, 'clk', 'clk', 'clk', 'clk', 'clk', 'clk', 1],
                     ['VDD', 'outp_a<0>', 'outn_a<0>', 'VDD',
                      'VSS', 'clkp', 'biasp_a', 'biasp_m', 'biasn_m', 'biasn_a', 'clkn', 'VSS'],
                     False)]
        else:
            sig_list = [(['out', 'out', 1, 'clk', 'clk', 1],
                         ['outp_a<0>', 'outn_a<0>', 'VDD', 'clkp', 'clkn', 'VDD'],
                         False),
                        ([1, 'clk', 'clk', 'clk', 'clk', 1, 1, 'casc', 'casc'],
                         ['VSS', 'biasp_a', 'biasp_m', 'biasn_m', 'biasn_a', 'VSS',
                          'VDD', 'cascp<1>', 'cascn<1>'],
                         True)]
            for idx in range(2, num_ffe):
                cascl = 'cascp<%d>' % idx
                cascr = 'cascn<%d>' % idx
                sig_list.append(([1, 'casc', 'casc'], ['VDD', cascl, cascr], True))
            return sig_list

    @classmethod
    def _get_dfe_signals(cls, num_dfe):
        if num_dfe == 1:
            return []
        elif num_dfe == 2:
            return [([1, 'out', 'out', 1, 1, 1, 1, 1, 1, 'clk', 'clk', 'clk', 'clk', 1],
                     ['VDD', 'outp_d<3>', 'outn_d<3>', 'VDD',
                      'sgnpp<3>', 'sgnnp<3>', 'sgnpn<3>', 'sgnnn<3>',
                      'VSS', 'biasp_d', 'biasp_s<3>', 'biasn_s<3>', 'biasn_d', 'VSS'],
                     False)]
        else:
            sig_list = [([1, 1, 1, 1, 1, 'clk', 'clk', 'clk', 'clk', 1],
                         ['sgnpp<3>', 'sgnnp<3>', 'sgnpn<3>', 'sgnnn<3>',
                          'VSS', 'biasp_d', 'biasp_s<3>', 'biasn_s<3>', 'biasn_d', 'VSS'],
                         False)]
            for dfe_idx in range(4, num_dfe + 1):
                suf = '<%d>' % dfe_idx
                sig_list.append(([1, 'clk', 'clk', 1, 1, 1, 1, 1],
                                 ['VSS', 'biasp_s' + suf, 'biasn_s' + suf, 'VSS',
                                  'sgnpp' + suf, 'sgnnp' + suf, 'sgnpn' + suf, 'sgnnn' + suf],
                                 True))
            suf = '<%d>' % (num_dfe + 1)
            sig_list.append(([1, 'clk', 'clk', 1, 1, 1, 1, 1, 1, 'out', 'out'],
                             ['VSS', 'biasp_s' + suf, 'biasn_s' + suf, 'VSS',
                              'sgnpp' + suf, 'sgnnp' + suf, 'sgnpn' + suf, 'sgnnn' + suf,
                              'VDD', 'outp_d' + suf, 'outn_d' + suf],
                             True))
            return sig_list

    def _create_and_place(self, tr_manager, num_inst, seg_list, seg_sum_list, flip_sign_list,
                          sig_list, end_mode, base_params, vm_layer, route_locs, place_info,
                          vdd_list, vss_list, blk_type, sig_off=0, sum_off=0, is_end=False,
                          left_out=True):
        vm_w_out = tr_manager.get_width(vm_layer, 'out')
        fg_dum = base_params['fg_duml']
        track_info = {}
        masters, sch_params, insts = [], [], []
        prev_data_w, prev_data_tr, prev_type, prev_tr, xarr = place_info
        left_out_b = not left_out
        for idx in range(num_inst - 1, -1, -1):
            sig_idx = idx + sig_off
            seg_lat = seg_list[idx]
            sig_types, sig_names, sig_right = sig_list[idx]
            seg_sum = seg_sum_list[idx + sum_off]
            flip_sign = flip_sign_list[idx + sum_off]

            # create master
            cur_params = base_params.copy()
            cur_params['seg_sum'] = seg_sum
            cur_params['seg_lat'] = seg_lat
            cur_params['flip_sign'] = flip_sign
            if is_end and (idx == num_inst - 1):
                cur_params['end_mode'] = end_mode | 0b0100
            cur_master = self.new_template(params=cur_params, temp_cls=TapXSummerCell)

            # check we can place current master without horizontal line-end spacing issues
            xcur = 0 if xarr is None else xarr - cur_master.array_box.left_unit
            if prev_data_tr is not None:
                data_xr = self.grid.get_wire_bounds(vm_layer, prev_data_tr, width=prev_data_w,
                                                    unit_mode=True)[1]
                xcur_min = data_xr - cur_master.get_vm_coord(prev_data_w, True, left_out_b)
                if xcur_min > xcur:
                    # need to increment left dummy fingers to avoid line-end spacing issues
                    sd_pitch = cur_master.sd_pitch
                    num_fg_inc = -(-(xcur_min - xcur) // (2 * sd_pitch)) * 2
                    cur_master = cur_master.new_template_with(fg_duml=fg_dum + num_fg_inc)

            # get minimum left routing track index
            data_xl = xcur + cur_master.get_vm_coord(vm_w_out, False, left_out)
            ltr = self.grid.find_next_track(vm_layer, data_xl, tr_width=vm_w_out,
                                            half_track=True, mode=1, unit_mode=True)
            # get total space needed for signals
            _, sig_locs = tr_manager.place_wires(vm_layer, sig_types)
            if prev_type is None:
                left_delta = sig_locs[0]
            else:
                _, left_locs = tr_manager.place_wires(vm_layer, [prev_type, sig_types[0]])
                left_delta = left_locs[1] - left_locs[0]
            if idx == 0:
                right_delta = 0
            else:
                _, right_locs = tr_manager.place_wires(vm_layer, [sig_types[-1], 1, 'out'])
                right_delta = right_locs[2] - right_locs[0]
            # compute minimum left routing track index
            ltr = max(ltr, prev_tr + left_delta + sig_locs[-1] - sig_locs[0] + right_delta)

            # record signal locations
            if sig_right:
                sig_offset = ltr - right_delta - sig_locs[-1]
            else:
                sig_offset = prev_tr + left_delta - sig_locs[0]
            for name, loc in zip(sig_names, sig_locs):
                self._record_track(track_info, name, loc + sig_offset)

            # add instance
            inst = self.add_instance(cur_master, 'X%s%d' % (blk_type.upper(), sig_idx),
                                     loc=(xcur, 0), unit_mode=True)
            vdd_list.extend(inst.port_pins_iter('VDD'))
            vss_list.extend(inst.port_pins_iter('VSS'))
            masters.append(cur_master)
            sch_params.append(cur_master.sch_params)
            insts.append(inst)
            xarr = inst.array_box.right_unit
            # record routing track locations, and update placement information
            if idx == 0:
                prev_data_w = tr_manager.get_width(vm_layer, sig_types[-2])
                prev_data_tr = sig_locs[-2] + sig_offset
                prev_type = sig_types[-1]
                prev_tr = sig_locs[-1] + sig_offset
            else:
                offset = ltr - route_locs[1]
                prev_data_w = vm_w_out
                prev_data_tr = route_locs[-2] + offset
                prev_type = 1
                prev_tr = route_locs[-1] + offset
                for x in range(0, 10, 3):
                    self._record_track(track_info, 'VDD', route_locs[x] + offset)
                self._record_track(track_info, 'outp_%s3<%d>' % (blk_type, sig_idx),
                                   route_locs[1] + offset)

                for cidx in range(1, 4):
                    x = 1 if cidx == 3 else (4 if cidx == 1 else 7)
                    self._record_track(track_info, 'outp_%s%d<%d>' % (blk_type, cidx, sig_idx),
                                       route_locs[x] + offset)
                    self._record_track(track_info, 'outn_%s%d<%d>' % (blk_type, cidx, sig_idx),
                                       route_locs[x + 1] + offset)

        insts.reverse()
        sch_params.reverse()
        place_info = prev_data_w, prev_data_tr, prev_type, prev_tr, xarr
        return masters, track_info, sch_params, insts, place_info

    @classmethod
    def _record_track(cls, track_info, name, tidx):
        if name in track_info:
            track_info[name].append(tidx)
        else:
            track_info[name] = [tidx]


class TapXSummer(TemplateBase):
    """The DFE tapx summer.

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

    _exclude_ports = {'clkp', 'clkn', 'VDD', 'VSS', 'outp_s', 'outn_s', 'en<0>', 'en<1>',
                      'en<2>', 'en<3>'}

    def __init__(self, temp_db, lib_name, params, used_names, **kwargs):
        # type: (TemplateDB, str, Dict[str, Any], Set[str], **kwargs) -> None
        TemplateBase.__init__(self, temp_db, lib_name, params, used_names, **kwargs)
        self._sch_params = None
        self._fg_core_last = None
        self._ffe_track_info = None
        self._dfe_track_info = None

    @property
    def sch_params(self):
        # type: () -> Dict[str, Any]
        return self._sch_params

    @property
    def fg_core_last(self):
        return self._fg_core_last

    @property
    def ffe_track_info(self):
        return self._ffe_track_info

    @property
    def dfe_track_info(self):
        return self._dfe_track_info

    @classmethod
    def get_default_param_values(cls):
        # type: () -> Dict[str, Any]
        return dict(
            div_pos_edge=True,
            fg_min_last=0,
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
            w_sum='NMOS/PMOS width dictionary for summer.',
            w_lat='NMOS/PMOS width dictionary for latch.',
            th_sum='NMOS/PMOS threshold flavor dictionary.',
            th_lat='NMOS/PMOS threshold dictoary for latch.',
            seg_sum_list='list of segment dictionaries for summer taps.',
            seg_ffe_list='list of segment dictionaries for FFE latches.',
            seg_dfe_list='list of segment dictionaries for DFE latches.',
            flip_sign_list='list of flip_sign values for summer taps.',
            seg_div='number of segments dictionary for clock divider.',
            seg_pul='number of segments dictionary for pulse generation.',
            fg_dum='Number of single-sided edge dummy fingers.',
            tr_widths='Track width dictionary.',
            tr_spaces='Track spacing dictionary.',
            div_pos_edge='True if the divider triggers off positive edge of the clock.',
            fg_min_last='Minimum number of core fingers for last cell.',
            is_end='True if this is the end row.',
            show_pins='True to create pin labels.',
            options='other AnalogBase options',
        )

    def draw_layout(self):
        # get parameters
        config = self.params['config']
        lch = self.params['lch']
        ptap_w = self.params['ptap_w']
        ntap_w = self.params['ntap_w']
        w_sum = self.params['w_sum']
        th_sum = self.params['th_sum']
        seg_sum_list = self.params['seg_sum_list']
        seg_ffe_list = self.params['seg_ffe_list']
        flip_sign_list = self.params['flip_sign_list']
        seg_div = self.params['seg_div']
        seg_pul = self.params['seg_pul']
        fg_dum = self.params['fg_dum']
        tr_widths = self.params['tr_widths']
        tr_spaces = self.params['tr_spaces']
        div_pos_edge = self.params['div_pos_edge']
        fg_min_last = self.params['fg_min_last']
        is_end = self.params['is_end']
        show_pins = self.params['show_pins']
        options = self.params['options']

        num_ffe = len(seg_ffe_list)
        end_mode = 1 if is_end else 0

        sub_params = self.params.copy()
        sub_params['show_pins'] = False
        sub_master = self.new_template(params=sub_params, temp_cls=TapXSummerNoLast)
        inst = self.add_instance(sub_master, 'XSUB', loc=(0, 0), unit_mode=True)
        self._ffe_track_info = sub_master.ffe_track_info
        self._dfe_track_info = sub_master.dfe_track_info.copy()
        vdd_list = inst.get_all_port_pins('VDD')
        vss_list = inst.get_all_port_pins('VSS')
        en_warrs = [list(inst.port_pins_iter('en<%d>' % idx)) for idx in range(4)]
        clkp_list = inst.get_all_port_pins('clkp')
        clkn_list = inst.get_all_port_pins('clkn')
        outsp = inst.get_pin('outp_s')
        outsn = inst.get_pin('outn_s')

        main = sub_master.analog_master
        last_params = dict(config=config, row_layout_info=main.lat_row_layout_info,
                           lch=lch, ptap_w=ptap_w, ntap_w=ntap_w, w_sum=w_sum, th_sum=th_sum,
                           seg_sum=seg_sum_list[num_ffe], seg_div=seg_div, seg_pul=seg_pul,
                           fg_duml=fg_dum, fg_dumr=fg_dum, tr_widths=tr_widths, tr_spaces=tr_spaces,
                           lat_tr_info=main.lat_track_info, div_pos_edge=div_pos_edge,
                           flip_sign=flip_sign_list[num_ffe], fg_min=fg_min_last,
                           end_mode=end_mode | 0b1000, show_pins=False, options=options
                           )
        last_master = self.new_template(params=last_params, temp_cls=TapXSummerLast)
        last_sch_params = last_master.sch_params
        xcur = inst.array_box.right_unit - last_master.array_box.left_unit
        instl = self.add_instance(last_master, 'XDFE2', loc=(xcur, 0), unit_mode=True)

        tr_manager = TrackManager(self.grid, tr_widths, tr_spaces, half_space=True)
        hm_layer = IntegAmp.get_mos_conn_layer(self.grid.tech_info) + 1
        vm_layer = hm_layer + 1
        vm_w_out = tr_manager.get_width(vm_layer, 'out')
        data_xl = xcur + last_master.get_vm_coord(vm_w_out)
        ltr = self.grid.find_next_track(vm_layer, data_xl, tr_width=vm_w_out, half_track=True,
                                        mode=1, unit_mode=True)
        vdd_list.extend(instl.port_pins_iter('VDD'))
        vss_list.extend(instl.port_pins_iter('VSS'))

        # set size
        self.set_size_from_bound_box(vm_layer, instl.bound_box.merge(inst.bound_box),
                                     round_up=True)
        self.array_box = self.bound_box

        # export last summer tap pins
        inp_pin = instl.get_pin('inp')
        inn_pin = instl.get_pin('inn')
        self.add_pin('inp_d<2>', inp_pin, show=show_pins)
        self.add_pin('inn_d<2>', inn_pin, show=show_pins)
        # add alias pins for column layout connection only
        self.add_pin('outp_d<2>', inp_pin, show=False)
        self.add_pin('outn_d<2>', inn_pin, show=False)
        self.reexport(instl.get_port('biasn'), net_name='biasn_s<2>', show=show_pins)
        if instl.has_port('casc<0>'):
            self.reexport(instl.get_port('casc<0>'), net_name='sgnp<2>', show=show_pins)
            self.reexport(instl.get_port('casc<1>'), net_name='sgnn<2>', show=show_pins)
        # TODO: handle setp/setn/pulse pins
        if instl.has_port('div'):
            for name in ('en_div', 'scan_div', 'div', 'divb'):
                self.reexport(instl.get_port(name), show=show_pins)
        # TODO: handle pulse generation pins

        # connect supplies
        vdd_list = self.connect_wires(vdd_list)
        vss_list = self.connect_wires(vss_list)
        self.add_pin('VDD', vdd_list, label='VDD:', show=show_pins)
        self.add_pin('VSS', vss_list, label='VSS:', show=show_pins)
        # connect outputs
        outsp = self.connect_wires([outsp, instl.get_pin('outp')])
        outsn = self.connect_wires([outsn, instl.get_pin('outn')])
        self.add_pin('outp_s', outsp, show=show_pins)
        self.add_pin('outn_s', outsn, show=show_pins)
        # connect clocks
        if instl.has_port('clkp'):
            clkp_list.extend(instl.port_pins_iter('clkp'))
        if instl.has_port('clkn'):
            clkn_list.extend(instl.port_pins_iter('clkn'))
        lower, upper = None, None
        for warr in chain(clkp_list, clkn_list):
            if lower is None:
                lower = warr.lower_unit
                upper = warr.upper_unit
            else:
                lower = min(lower, warr.lower_unit)
                upper = max(upper, warr.upper_unit)
        clkp = self.connect_wires(clkp_list, lower=lower, upper=upper, unit_mode=True)
        clkn = self.connect_wires(clkn_list, lower=lower, upper=upper, unit_mode=True)
        self.add_pin('clkp', clkp, label='clkp:', show=show_pins)
        self.add_pin('clkn', clkn, label='clkn:', show=show_pins)
        # connect enables
        en_warrs[2].extend(instl.port_pins_iter('en<2>'))
        if instl.has_port('en<1>'):
            en_warrs[1].extend(instl.port_pins_iter('en<1>'))
        for idx, en_warr in enumerate(en_warrs):
            if en_warr:
                en_warr = self.connect_wires(en_warr)
                name = 'en<%d>' % idx
                self.add_pin(name, en_warr, label=name + ':', show=show_pins)

        # re-export rest of the pins
        for name in inst.port_names_iter():
            if name not in self._exclude_ports:
                if name.startswith('outp_') or name.startswith('outn_'):
                    label = name + ':'
                else:
                    label = ''
                self.reexport(inst.get_port(name), label=label, show=show_pins)

        self._sch_params = dict(
            ffe_params_list=sub_master.sch_params['ffe_params_list'],
            dfe_params_list=sub_master.sch_params['dfe_params_list'],
            last_params=last_sch_params,
        )
        self._fg_core_last = last_master.fg_core


class TapXColumn(TemplateBase):
    """The column of DFE tap1 summers.

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
            w_sum='NMOS/PMOS width dictionary for summer.',
            w_lat='NMOS/PMOS width dictionary for latch.',
            th_sum='NMOS/PMOS threshold flavor dictionary.',
            th_lat='NMOS/PMOS threshold dictionary for latch.',
            seg_sum_list='list of segment dictionaries for summer taps.',
            seg_ffe_list='list of segment dictionaries for FFE latches.',
            seg_dfe_list='list of segment dictionaries for DFE latches.',
            flip_sign_list='list of flip_sign values for summer taps.',
            seg_div='number of segments dictionary for clock divider.',
            seg_pul='number of segments dictionary for pulse generation.',
            fg_dum='Number of single-sided edge dummy fingers.',
            tr_widths='Track width dictionary.',
            tr_spaces='Track spacing dictionary.',
            show_pins='True to create pin labels.',
            options='other AnalogBase options',
        )

    def draw_layout(self):
        # get parameters
        show_pins = self.params['show_pins']
        tr_widths = self.params['tr_widths']
        tr_spaces = self.params['tr_spaces']

        # make masters
        div_params = self.params.copy()
        div_params['seg_pul'] = None
        div_params['div_pos_edge'] = True
        div_params['is_end'] = False
        div_params['show_pins'] = False

        divn_master = self.new_template(params=div_params, temp_cls=TapXSummer)
        fg_min_last = divn_master.fg_core_last

        end_params = self.params.copy()
        end_params['seg_div'] = None
        end_params['fg_min_last'] = fg_min_last
        end_params['is_end'] = True
        end_params['show_pins'] = False

        endb_master = self.new_template(params=end_params, temp_cls=TapXSummer)
        if endb_master.fg_core_last > fg_min_last:
            fg_min_last = endb_master.fg_core_last
            divn_master = divn_master.new_template_with(fg_min_last=fg_min_last)

        divp_master = divn_master.new_template_with(div_pos_edge=False)
        endt_master = endb_master.new_template_with(seg_pul=None)

        # place instances
        vm_layer = endt_master.top_layer
        inst3 = self.add_instance(endb_master, 'X3', loc=(0, 0), unit_mode=True)
        ycur = inst3.array_box.top_unit + divn_master.array_box.top_unit
        inst0 = self.add_instance(divp_master, 'X0', loc=(0, ycur), orient='MX', unit_mode=True)
        ycur = inst0.array_box.top_unit
        inst2 = self.add_instance(divn_master, 'X2', loc=(0, ycur), unit_mode=True)
        ycur = inst2.array_box.top_unit + endt_master.array_box.top_unit
        inst1 = self.add_instance(endt_master, 'X1', loc=(0, ycur), orient='MX', unit_mode=True)
        inst_list = [inst0, inst1, inst2, inst3]

        # set size
        self.set_size_from_bound_box(vm_layer, inst1.bound_box.merge(inst3.bound_box))
        self.array_box = self.bound_box

        # re-export supply pins
        vdd_list = list(chain(*(inst.port_pins_iter('VDD') for inst in inst_list)))
        vss_list = list(chain(*(inst.port_pins_iter('VSS') for inst in inst_list)))
        self.add_pin('VDD', vdd_list, label='VDD:', show=show_pins)
        self.add_pin('VSS', vss_list, label='VSS:', show=show_pins)

        # draw wires
        tr_manager = TrackManager(self.grid, tr_widths, tr_spaces, half_space=True)

        # re-export ports, and gather wires
        en_warrs = [[], [], [], []]
        biasm_warrs = [0, 0, 0, 0]
        clk_warrs = [[], []]
        biasa_warrs = [[], []]
        biasd_warrs = [[], []]
        for idx, inst in enumerate(inst_list):
            nidx = (idx - 1) % 4
            biasm_warrs[nidx] = inst.get_pin('biasn_m')
            for off in range(4):
                en_pin = 'en<%d>' % off
                en_idx = (off + idx + 1) % 4
                if inst.has_port(en_pin):
                    en_warrs[en_idx].extend(inst.port_pins_iter(en_pin))
            if inst.has_port('div'):
                if idx == 0:
                    idxp, idxn = 3, 1
                else:
                    idxp, idxn = 2, 0
                en_warrs[idxp].extend(inst.port_pins_iter('div'))
                en_warrs[idxn].extend(inst.port_pins_iter('divb'))

            self.reexport(inst.get_port('outp_s'), net_name='outp<%d>' % nidx, show=show_pins)
            self.reexport(inst.get_port('outn_s'), net_name='outn<%d>' % nidx, show=show_pins)
            if idx % 2 == 1:
                biasa_warrs[0].extend(inst.port_pins_iter('biasp_a'))
                biasd_warrs[0].extend(inst.port_pins_iter('biasp_d'))
                clk_warrs[0].extend(inst.port_pins_iter('clkp'))
                clk_warrs[1].extend(inst.port_pins_iter('clkn'))
            else:
                biasa_warrs[1].extend(inst.port_pins_iter('biasp_a'))
                biasd_warrs[1].extend(inst.port_pins_iter('biasp_d'))
                clk_warrs[1].extend(inst.port_pins_iter('clkp'))
                clk_warrs[0].extend(inst.port_pins_iter('clkn'))

        # connect DFE/FFE signals
        vm_w_out = tr_manager.get_width(vm_layer, 'out')
        _, route_locs = tr_manager.place_wires(vm_layer, [1, 'out', 'out', 1, 'out', 'out', 1,
                                                          'out', 'out', 1])
        tmp = self._connect_signals(route_locs, endb_master.ffe_tracks, inst_list, vm_layer,
                                    vm_w_out, 'a', sig_off=0, is_ffe=True)
        shields_ffe = tmp[2]
        for warrp, warrn in zip(tmp[0], tmp[1]):
            self.add_pin('inp_a', warrp, label='inp_a:', show=show_pins)
            self.add_pin('inn_a', warrn, label='inn_a:', show=show_pins)

        tmp = self._connect_signals(route_locs, endb_master.dfe_tracks, inst_list, vm_layer,
                                    vm_w_out, 'd', sig_off=2, is_ffe=False)
        shields_dfe = tmp[2]
        for cidx, (warrp, warrn) in enumerate(zip(tmp[0], tmp[1])):
            self.add_pin('inp_d<%d>' % cidx, warrp, show=show_pins)
            self.add_pin('inn_d<%d>' % cidx, warrn, show=show_pins)

        # connect cascode
        shields_casc = self._connect_cascode(inst_list, vm_layer, tr_manager,
                                             shields_ffe, show_pins)
        # connect analog latch and main summer clocks
        shields_ana = self._connect_clk_analog(inst_list, vm_layer, tr_manager,
                                               shields_casc, show_pins)

        # connect shield wires
        sh_lower, sh_upper = None, None
        for tr_idx in shields_ana:
            warr = self.connect_to_tracks(vss_list, TrackID(vm_layer, tr_idx))
            if sh_lower is None:
                sh_lower = warr.lower_unit
                sh_upper = warr.upper_unit
        for tr_idx in chain(shields_ffe, shields_dfe, shields_casc):
            self.connect_to_tracks(vdd_list, TrackID(vm_layer, tr_idx), track_lower=sh_lower,
                                   track_upper=sh_upper, unit_mode=True)

    def _connect_clk_analog(self, inst_list, vm_layer, tr_manager, shields_casc, show_pins):
        vm_w = tr_manager.get_width(vm_layer, 'clk')
        _, route_locs = tr_manager.place_wires(vm_layer, [1, 'clk', 'clk', 'clk', 'clk', 1, 1])
        offset = shields_casc[-1] - route_locs[-1]
        clkp_warrs, clkn_warrs, m_warrs = [], [], []
        for cidx, inst in enumerate(inst_list):
            warr_a = inst.get_pin('biasp_a')
            if cidx % 2 == 1:
                clkp_warrs.append(warr_a)
            else:
                clkn_warrs.append(warr_a)
            m_warrs.append(inst_list[(cidx + 1) % 4].get_pin('biasn_m'))

        trp, trn = route_locs[1] + offset, route_locs[4] + offset
        wp, wn = self.connect_differential_tracks(clkp_warrs, clkn_warrs, vm_layer, trp, trn,
                                                  width=vm_w)
        self.add_pin('biasp_a', wp, show=show_pins)
        self.add_pin('biasn_a', wn, show=show_pins)
        trp, trn = route_locs[2] + offset, route_locs[3] + offset
        wp, wn = self.connect_differential_tracks(m_warrs[1], m_warrs[0], vm_layer, trp, trn,
                                                  width=vm_w)
        self.add_pin('bias_m<1>', wp, show=show_pins)
        self.add_pin('bias_m<0>', wn, show=show_pins)
        wp, wn = self.connect_differential_tracks(m_warrs[3], m_warrs[2], vm_layer, trp, trn,
                                                  width=vm_w)
        self.add_pin('bias_m<3>', wp, show=show_pins)
        self.add_pin('bias_m<2>', wn, show=show_pins)

        return [route_locs[0] + offset, route_locs[5] + offset]

    def _connect_cascode(self, inst_list, vm_layer, tr_mananger, shields_ffe, show_pins):
        vm_w = tr_mananger.get_width(vm_layer, 'casc')
        _, route_locs = tr_mananger.place_wires(vm_layer, [1, 'casc', 'casc', 1])
        num_ffe = (len(shields_ffe) - 1) // 4 + 1
        shields_casc = []
        for ffe_idx in range(num_ffe - 1, 0, -1):
            sh_right = shields_ffe[4 * (num_ffe - 1 - ffe_idx)]
            offset = sh_right - route_locs[3]
            shields_casc.append(route_locs[0] + offset)
            for cidx, inst in enumerate(inst_list):
                warr = inst.get_pin('casc<%d>' % ffe_idx)
                tidx = route_locs[1] + offset if cidx % 2 == 0 else route_locs[2] + offset
                min_len_mode = 1 if 1 <= cidx <= 2 else -1
                warr = self.connect_to_tracks(warr, TrackID(vm_layer, tidx, width=vm_w),
                                              min_len_mode=min_len_mode)
                self.add_pin('casc<%d>' % (cidx + ffe_idx * 4), warr, show=show_pins)

        return shields_casc

    def _connect_signals(self, route_locs, track_locs, inst_list, vm_layer, vm_width, sig_type,
                         sig_off=0, is_ffe=True):
        in_dir = 1 if is_ffe else -1
        num_sig = len(track_locs) + 1

        # collect signal wires
        sigp_dict, sign_dict = {}, {}
        for cidx, inst in enumerate(inst_list):
            pcidx = (cidx + 1) % 4
            for sidx in range(sig_off, num_sig + sig_off):
                key = (sidx, cidx)
                if key not in sigp_dict:
                    sigp_dict[key] = []
                if key not in sign_dict:
                    sign_dict[key] = []
                sigp_dict[key].extend(inst.port_pins_iter('outp_%s<%d>' % (sig_type, sidx)))
                sign_dict[key].extend(inst.port_pins_iter('outn_%s<%d>' % (sig_type, sidx)))

                key = (sidx + in_dir, pcidx)
                if key not in sigp_dict:
                    sigp_dict[key] = []
                if key not in sign_dict:
                    sign_dict[key] = []
                sigp_dict[key].extend(inst.port_pins_iter('inp_%s<%d>' % (sig_type, sidx)))
                sign_dict[key].extend(inst.port_pins_iter('inn_%s<%d>' % (sig_type, sidx)))

        # compute connection parameters based on end_first flag.
        inp_list, inn_list, shield_list = [], [], []
        diff_shield = route_locs[1] - route_locs[0]
        diff_sep = route_locs[2] - route_locs[1]
        if is_ffe:
            tr_const = num_sig + sig_off - 1
            sig_range = range(1 + sig_off, tr_const + 1)
            tr_shield = route_locs[-1] + track_locs[-1] - route_locs[1]
            end_trp = tr_shield + diff_shield
            end_trn = end_trp + diff_sep
            shield_list.append(end_trn + diff_shield)
            # add FFE inputs
            in_idx = num_sig + sig_off - 1 + in_dir
            for cidx in range(4):
                inp_list.append(sigp_dict[(in_idx, cidx)])
                inn_list.append(sign_dict[(in_idx, cidx)])
        else:
            tr_const = num_sig + sig_off - 2
            sig_range = range(sig_off, tr_const + 1)
            tr_shield = route_locs[0] + track_locs[0] - route_locs[1]
            end_trn = tr_shield - diff_shield
            end_trp = end_trn - diff_sep
            shield_list.append(end_trp - diff_shield)

        # connect intermediate signals
        sh_idx_list = [0, 3, 6, 9]
        for sidx in sig_range:
            ltr = track_locs[tr_const - sidx]
            offset = ltr - route_locs[1]
            shield_list.extend((route_locs[x] + offset for x in sh_idx_list))
            for cidx in range(4):
                key = (sidx, cidx)
                if cidx == 3:
                    idxp = 1
                elif cidx == 1:
                    idxp = 4
                else:
                    idxp = 7
                trp, trn = route_locs[idxp] + offset, route_locs[idxp + 1] + offset
                warrp, warrn = sigp_dict[key], sign_dict[key]
                vwp, vwn = self.connect_differential_tracks(warrp, warrn, vm_layer, trp, trn,
                                                            width=vm_width)
                if not is_ffe and sidx == sig_off:
                    # for DFE, export inputs on vertical layer.
                    inp_list.append(vwp)
                    inn_list.append(vwn)

        # copnnect end signals
        sidx = sig_off if is_ffe else num_sig + sig_off - 1
        for cidx in range(4):
            key = (sidx, cidx)
            self.connect_differential_tracks(sigp_dict[key], sign_dict[key], vm_layer,
                                             end_trp, end_trn, width=vm_width)

        shield_list.sort()
        return inp_list, inn_list, shield_list
