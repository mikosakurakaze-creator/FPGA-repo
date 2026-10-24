"""Independent boundary tests; run with python -m unittest ...fixed.test_numeric."""
import unittest
from fractions import Fraction
import numpy as np
from .numeric import round_shift,input_rgb8,display_rgb8

class ArithmeticTests(unittest.TestCase):
    def test_round_shift_signed_ties_and_extremes(self):
        values=[-(1<<63),-(1<<63)+1,-999,-5,-3,-1,0,1,3,5,999,(1<<63)-1]
        for shift in (0,1,2,7,16,31,62):
            actual=round_shift(np.array(values,dtype=np.int64),shift).tolist()
            expected=[]
            for value in values:
                n=abs(value);q,r=divmod(n,1<<shift)
                expected.append((q+int(2*r >= (1<<shift)))*(1 if value >= 0 else -1))
            self.assertEqual(actual,expected)
        with self.assertRaises(OverflowError):round_shift(np.array([(1<<63)-1],np.int64),-1)

    def test_all_rgb_codes_exact_fraction(self):
        rgb=np.broadcast_to(np.arange(256,dtype=np.uint8)[None,:,None],(1,256,3)).copy()
        actual=input_rgb8(rgb,14)[0,0,0].tolist()
        expected=[]
        for value in range(256):
            n=(2*value-255)*16384;q,r=divmod(abs(n),255)
            expected.append((q+int(r*2>=255))*(1 if n>=0 else -1))
        self.assertEqual(actual,expected)
        self.assertEqual(actual[0],-16384);self.assertEqual(actual[-1],16384)

    def test_display_exhaustive_bankers(self):
        # Exact independent rational arithmetic covers every possible output INT16.
        values=np.arange(-32768,32768,dtype=np.int32).astype(np.int16)
        tensor=np.broadcast_to(values.reshape(1,1,1,-1),(1,3,1,65536)).copy()
        actual=display_rgb8(tensor)[0,:,0].tolist()
        expected=[round(Fraction(min(max(int(v),0),16384)*255,16384)) for v in values]
        self.assertEqual(actual,expected)
        # v=8192 =>127.5 rounds128; even/odd midpoint tests are exercised above.

if __name__=='__main__':unittest.main()
