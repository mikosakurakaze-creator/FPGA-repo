import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from data import audit_manifest
from integer import round_div, conv_integer, calibrate, IntegerRestore, tiled_integer
from model import TinyRestore,tiled_forward,engineering_profile


class PipelineTests(unittest.TestCase):
    def test_tiling_matches_full_with_nonzero_tail_and_odd_boundaries(self):
        torch.manual_seed(1)
        model=TinyRestore(8,3).eval()
        torch.nn.init.normal_(model.tail.weight,std=.05)
        x=torch.rand(1,3,37,43)
        with torch.inference_mode():
            expected=model(x)
            for core in (7,16,64):
                actual=tiled_forward(model,x,core)
                self.assertLess(float((actual-expected).abs().max()),2e-6)

    def test_signed_nearest_even(self):
        np.testing.assert_array_equal(round_div(np.arange(-7,8),1),
            [-4,-3,-2,-2,-2,-1,0,0,0,1,2,2,2,3,4])

    def test_integer_dense_and_depthwise_match_independent_torch_double(self):
        rng=np.random.default_rng(3)
        for groups,out in ((1,4),(3,3)):
            x=rng.integers(-100,101,(1,3,9,7),dtype=np.int64)
            w=rng.integers(-10,11,(out,3//groups,3,3),dtype=np.int64)
            b=rng.integers(-50,51,out,dtype=np.int64)
            actual,_=conv_integer(x,w,b,groups,1)
            expected=torch.nn.functional.conv2d(torch.from_numpy(x).double(),torch.from_numpy(w).double(),
                torch.from_numpy(b).double(),padding=1,groups=groups).numpy().astype(np.int64)
            np.testing.assert_array_equal(actual,expected)

    def test_accumulator_overflow_is_rejected(self):
        x=np.full((1,3,2,2),32767,dtype=np.int64)
        w=np.full((1,3,1,1),127,dtype=np.int64)
        with self.assertRaises(OverflowError):conv_integer(x,w,[2147483647])

    def test_integer_nonzero_model_close_to_float(self):
        torch.manual_seed(4)
        model=TinyRestore(8,2).eval()
        torch.nn.init.normal_(model.tail.weight,std=.02)
        a=torch.rand(3,13,17)
        spec,weights=calibrate(model,[(a,a,'a')],1)
        integer=IntegerRestore(spec,weights)
        q=integer(np.rint(a[None].numpy()*16384).astype(np.int16))/16384
        with torch.inference_mode():fp=model(a[None]).clamp(0,1).numpy()
        self.assertLess(float(np.max(np.abs(q-fp))),.01)

    def test_profile_full_resolution_and_overlap(self):
        p=engineering_profile(TinyRestore(8,5),720,1272,128,30)
        self.assertEqual(p['macs_per_frame'],720*1272*(27*8+5*(9*8+8*8)+3*8))
        self.assertGreater(p['tiled_macs_per_frame'],p['macs_per_frame'])

    def test_integer_tiling_is_bit_exact(self):
        torch.manual_seed(12)
        model=TinyRestore(8,2).eval()
        torch.nn.init.normal_(model.tail.weight,std=.03)
        a=torch.rand(3,19,23)
        spec,weights=calibrate(model,[(a,a,'a')],1)
        integer=IntegerRestore(spec,weights)
        x=np.rint(a[None].numpy()*16384).astype(np.int16)
        expected=integer(x)
        np.testing.assert_array_equal(tiled_integer(integer,x,7),expected)

    def test_clean_pixel_leakage_rejected_even_with_different_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            rows=[]
            for i,split in enumerate(('train','val','test')):
                pixels=np.full((9,9,3),100,dtype=np.uint8)
                Image.fromarray(pixels).save(root/f'{i}.png')
                rows.append({'id':str(i),'clean_id':str(i),'split':split,
                             'input':f'{i}.png','target':f'{i}.png'})
            manifest=root/'manifest.json'
            manifest.write_text(json.dumps({'task':'derain','pairs':rows}))
            with self.assertRaisesRegex(ValueError,'leakage'):audit_manifest(manifest)


if __name__=='__main__':unittest.main()
