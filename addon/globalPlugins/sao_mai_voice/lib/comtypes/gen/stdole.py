from enum import IntFlag

import comtypes.gen._00020430_0000_0000_C000_000000000046_0_2_0 as __wrapper_module__
from comtypes.gen._00020430_0000_0000_C000_000000000046_0_2_0 import (
    FONTSTRIKETHROUGH, OLE_HANDLE, OLE_YPOS_PIXELS, OLE_COLOR,
    Monochrome, StdFont, dispid, Checked, HRESULT,
    OLE_XSIZE_CONTAINER, Picture, CoClass, IPicture, IPictureDisp,
    FONTSIZE, IEnumVARIANT, OLE_XPOS_CONTAINER, OLE_XPOS_HIMETRIC,
    COMMETHOD, StdPicture, IFontDisp, Gray, DISPPROPERTY, IFont,
    OLE_YSIZE_HIMETRIC, Default, FONTUNDERSCORE,
    OLE_ENABLEDEFAULTBOOL, FONTBOLD, OLE_YSIZE_CONTAINER, DISPMETHOD,
    Unchecked, FontEvents, BSTR, OLE_OPTEXCLUSIVE, FONTITALIC,
    OLE_YPOS_HIMETRIC, IUnknown, EXCEPINFO, OLE_XSIZE_HIMETRIC,
    _check_version, OLE_CANCELBOOL, IDispatch, GUID, typelib_path,
    OLE_YPOS_CONTAINER, _lcid, FONTNAME, Font, VARIANT_BOOL, Library,
    DISPPARAMS, IFontEventsDisp, Color, VgaColor, OLE_XSIZE_PIXELS,
    OLE_YSIZE_PIXELS, OLE_XPOS_PIXELS
)


class OLE_TRISTATE(IntFlag):
    Unchecked = 0
    Checked = 1
    Gray = 2


class LoadPictureConstants(IntFlag):
    Default = 0
    Monochrome = 1
    VgaColor = 2
    Color = 4


__all__ = [
    'OLE_ENABLEDEFAULTBOOL', 'FONTBOLD', 'FONTSTRIKETHROUGH',
    'OLE_HANDLE', 'OLE_YPOS_PIXELS', 'OLE_YSIZE_CONTAINER',
    'OLE_COLOR', 'Monochrome', 'Unchecked', 'FontEvents', 'StdFont',
    'OLE_OPTEXCLUSIVE', 'Checked', 'FONTITALIC', 'OLE_YPOS_HIMETRIC',
    'OLE_XSIZE_CONTAINER', 'Picture', 'OLE_XSIZE_HIMETRIC',
    'IPicture', 'IPictureDisp', 'LoadPictureConstants',
    'OLE_CANCELBOOL', 'typelib_path', 'OLE_TRISTATE',
    'OLE_YPOS_CONTAINER', 'FONTSIZE', 'FONTNAME', 'Font',
    'OLE_XPOS_CONTAINER', 'OLE_XPOS_HIMETRIC', 'Library',
    'IFontEventsDisp', 'Color', 'VgaColor', 'StdPicture', 'IFontDisp',
    'Gray', 'IFont', 'OLE_YSIZE_HIMETRIC', 'Default',
    'OLE_XSIZE_PIXELS', 'OLE_YSIZE_PIXELS', 'FONTUNDERSCORE',
    'OLE_XPOS_PIXELS'
]

