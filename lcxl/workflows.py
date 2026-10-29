"""Pure draft operations. All operations validate before replacing any controls."""
from copy import deepcopy
from dataclasses import fields
from datetime import datetime, timezone
import base64, json
from pathlib import Path
from .protocol import Control, control_signature, control_record, encode_mode, parse_mode
from .library import atomic_write


def family(cid):
    return 'knob' if cid < 40 else 'fader' if cid < 48 else 'button'


def row_ids(cid):
    start=16+((cid-16)//8)*8
    return list(range(start,start+8))


def paste_controls(mode, copied, targets):
    if len(copied)!=len(targets):
        raise ValueError('Select the same number of destination controls as the copied selection.')
    result=deepcopy(mode)
    for source,cid in zip(copied,targets):
        if family(source.id)!=family(cid):
            raise ValueError('Paste into the same kind of control: knobs, faders or buttons.')
        if source.kind=='unknown':
            raise ValueError('An unknown imported message cannot be copied safely.')
        c=deepcopy(source); c.id=cid; c.raw=b''
        control_record(c); result.controls[cid]=c
    encode_mode(result)
    return result


def batch_controls(mode, ids, changes):
    if not changes or not ids: raise ValueError('Choose controls and at least one setting to change.')
    if not set(changes)<= {'color','on_color','channel','low','high'}:
        raise ValueError('Unsupported group setting.')
    result=deepcopy(mode)
    for cid in ids:
        c=result.controls[cid]
        if c.kind in ('disabled','unknown','Key'):
            raise ValueError('Select assigned MIDI controls only; keyboard shortcuts cannot be edited as a group.')
        if 'color' in changes and family(cid)=='fader':
            raise ValueError('Faders have no LED color. Deselect faders or turn off LED color.')
        if 'on_color' in changes and family(cid)!='button':
            raise ValueError('The ON color is available for buttons only.')
        if set(changes)&{'low','high'} and (c.kind=='Note' or c.relative):
            raise ValueError('Value ranges require absolute CC, NRPN or Program Change controls.')
        for key,value in changes.items(): setattr(c,key,value)
        try:control_record(c)
        except ValueError as ex:
            limit=16383 if c.kind in ('CC14','NRPN14') else 127
            raise ValueError(f'{family(cid).capitalize()} {(cid-16)%8+1}, {c.label or c.kind}: {c.kind} minimum and maximum must be 0–{limit}. Check the selected settings. ({ex})') from ex
    encode_mode(result)
    return result


def differences(mode, baseline, ids=None):
    """Human-readable field diffs against the last readback (never a fresh-read claim)."""
    rows=[]
    if ids is None and (baseline is None or mode.name!=baseline.name):
        rows.append(('Mode name','Name',baseline.name if baseline else 'Not read',mode.name))
    for cid in (range(16,64) if ids is None else ids):
        c=mode.controls[cid]; old=baseline.controls[cid] if baseline else None
        if old and control_signature(c)==control_signature(old): continue
        position=(f'Knob {(cid-16)%8+1} / row {(cid-16)//8+1}' if cid<40 else
                  f'Fader {cid-39}' if cid<48 else f'Button {(cid-48)%8+1} / row {(cid-48)//8+1}')
        for f in fields(Control):
            if f.name in ('id','raw'): continue
            value=getattr(c,f.name); previous=getattr(old,f.name) if old else 'Not read'
            if old is None or value!=previous:
                rows.append((position,f.name.replace('_',' ').capitalize(),
                             'Global' if previous is None else str(previous),
                             'Global' if value is None else str(value)))
        if old and not any(r[0]==position for r in rows):
            rows.append((position,'Imported definition','Stored bytes','Changed bytes'))
    return rows


class DraftStore:
    def __init__(self,root): self.path=Path(root)/'drafts'/'recovery.json'
    def save(self,mode,baseline,slot,device):
        obj={'version':1,'saved_at':datetime.now(timezone.utc).isoformat(),'slot':slot,'device':device,
             'mode':base64.b64encode(encode_mode(mode)).decode('ascii'),
             'baseline':base64.b64encode(encode_mode(baseline)).decode('ascii') if baseline else None}
        atomic_write(self.path,json.dumps(obj).encode('utf8'))
    def load(self):
        if not self.path.exists(): return None
        if self.path.stat().st_size>262144: raise ValueError('Recovery file is too large.')
        obj=json.loads(self.path.read_text(encoding='utf8'))
        if obj.get('version')!=1 or obj.get('slot') not in (None,*range(1,16)):
            raise ValueError('Unsupported recovery file.')
        obj['mode']=parse_mode(base64.b64decode(obj['mode'],validate=True))
        obj['baseline']=parse_mode(base64.b64decode(obj['baseline'],validate=True),obj['slot']) if obj.get('baseline') else None
        return obj
    def clear(self): self.path.unlink(missing_ok=True)
