"""ReID embedders for person crops. All return L2-normalised float32 [N, D] numpy arrays.

Backends: osnet (OSNet-AIN x1.0 MSMT17 via BoxMOT), clipreid (CLIP-ReID ViT-B/16 MSMT17),
plip (PLIP ModifiedResNet50, zero-shot person representation + text queries), dinov2 (generic baseline).
Weights live in ~/.cache/epicenv/weights; third-party code in ~/Workspace/.cache/thirdparty.
"""
import os, sys, pathlib
import numpy as np, torch, cv2
import torch.nn.functional as F

W = pathlib.Path.home() / '.cache/epicenv/weights'
TP = pathlib.Path.home() / 'Workspace/.cache/thirdparty/github.com'
DEV = 'cuda'


def _load_rgb(paths, h, w):
    ims = []
    for p in paths:
        im = cv2.imread(str(p))[:, :, ::-1]
        ims.append(cv2.resize(im, (w, h), interpolation=cv2.INTER_CUBIC))
    return torch.from_numpy(np.stack(ims)).permute(0, 3, 1, 2).float() / 255.0


def _norm(x, mean, std):
    m = torch.tensor(mean).view(1, 3, 1, 1); s = torch.tensor(std).view(1, 3, 1, 1)
    return (x - m) / s


class Base:
    H, W, MEAN, STD, BS = 256, 128, (0.485, 0.456, 0.406), (0.229, 0.224, 0.225), 128

    @torch.no_grad()
    def __call__(self, paths, flip=True):
        out = []
        for i in range(0, len(paths), self.BS):
            x = _norm(_load_rgb(paths[i:i + self.BS], self.H, self.W), self.MEAN, self.STD).to(DEV)
            f = self.fwd(x)
            if flip:
                f = f + self.fwd(torch.flip(x, dims=[3]))
            out.append(F.normalize(f.float(), dim=1).cpu())
        return torch.cat(out).numpy() if out else np.zeros((0, 1), np.float32)


class OSNet(Base):
    def __init__(self):
        from boxmot.reid import create_reid_encoder
        enc = create_reid_encoder('osnet_ain_x1_0_msmt17', device='cuda:0', precision='fp32')
        # find the torch module inside the encoder
        self.m = None
        for obj in [enc] + list(vars(enc).values()):
            for v in ([obj] + list(vars(obj).values()) if hasattr(obj, '__dict__') else [obj]):
                if isinstance(v, torch.nn.Module):
                    self.m = v; break
            if self.m is not None:
                break
        assert self.m is not None, 'osnet module not found'
        self.m.eval().to(DEV)

    def fwd(self, x):
        f = self.m(x)
        return f[0] if isinstance(f, (tuple, list)) else f


class CLIPReID(Base):
    MEAN = STD = (0.5, 0.5, 0.5)

    def __init__(self):
        sys.path.insert(0, str(TP / 'Syliz517/CLIP-ReID'))
        from model.clip import clip
        url = clip._MODELS['ViT-B-16']
        sd = torch.jit.load(clip._download(url), map_location='cpu').state_dict()
        cm = clip.build_model(sd, 16, 8, 16)  # 256x128 input, stride 16
        self.v = cm.visual.float()
        ck = torch.load(W / 'clipreid_msmt17_vitb16.pth', map_location='cpu')
        vis = {k[len('image_encoder.'):]: v for k, v in ck.items() if k.startswith('image_encoder.')}
        missing = self.v.load_state_dict(vis, strict=False)
        assert not missing.missing_keys, missing.missing_keys[:5]
        self.v.eval().to(DEV)

    def fwd(self, x):
        last, feat, proj = self.v(x)
        return torch.cat([feat[:, 0], proj[:, 0]], dim=1)


class PLIP(Base):
    MEAN, STD = (0.357, 0.323, 0.328), (0.252, 0.242, 0.239)

    def __init__(self, text=False):
        sys.path.insert(0, str(TP / 'Zplusdragon/PLIP'))
        from visual_model import Image_encoder_ModifiedResNet
        ck = torch.load(W / 'PLIP_RN50.pth.tar', map_location='cpu', weights_only=False)
        self.m = Image_encoder_ModifiedResNet([3, 4, 6, 3], 768, 8, input_resolution=[128, 256])
        self.m.load_state_dict(ck['ImgEncoder_state_dict'])
        self.m.eval().to(DEV)
        self.t = None
        if text:
            from textual_model import Textual_encoder
            self.t = Textual_encoder(encoder_type='bert-base-uncased')
            sd = {k: v for k, v in ck['TxtEncoder_state_dict'].items() if not k.endswith('position_ids')}
            self.t.load_state_dict(sd, strict=False)
            self.t.eval().to(DEV)

    def fwd(self, x):
        return self.m(x)[0]

    @torch.no_grad()
    def text(self, sentences):
        from transformers import BertTokenizer
        tok = BertTokenizer.from_pretrained('bert-base-uncased')
        b = tok(sentences, padding='max_length', max_length=64, truncation=True, return_tensors='pt')
        f = self.t.get_global_embedding(b['input_ids'].to(DEV), b['attention_mask'].to(DEV))
        return F.normalize(f.float(), dim=1).cpu().numpy()


class DINOv2(Base):
    H, W = 224, 112

    def __init__(self):
        from transformers import AutoModel
        self.m = AutoModel.from_pretrained('facebook/dinov2-base').eval().to(DEV)

    def fwd(self, x):
        o = self.m(pixel_values=x).last_hidden_state
        return torch.cat([o[:, 0], o[:, 1:].mean(1)], dim=1)


MODELS = {'osnet': OSNet, 'clipreid': CLIPReID, 'plip': PLIP, 'dinov2': DINOv2}


def get(name, **kw):
    return MODELS[name](**kw)


if __name__ == '__main__':
    d = pathlib.Path(sys.argv[1])
    from collections import defaultdict
    g = defaultdict(list)
    for p in sorted(d.glob('*.jpg')):
        g[p.name[:6]].append(p)
    ps = [x for k in sorted(g, key=lambda k: -len(g[k]))[:16] for x in g[k][::max(1, len(g[k]) // 4)][:4]]
    for n in sys.argv[2:] or MODELS:
        e = get(n)(ps)
        tid = np.array([p.name[:6] for p in ps])
        s = e @ e.T
        same = (tid[:, None] == tid[None]) & ~np.eye(len(ps), dtype=bool)
        print(n, e.shape, 'same-track sim %.3f  diff-track sim %.3f' % (s[same].mean(), s[~same & ~np.eye(len(ps), dtype=bool)].mean()))
