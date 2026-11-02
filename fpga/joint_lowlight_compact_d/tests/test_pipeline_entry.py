import unittest
from types import SimpleNamespace

from controller import Buffer
from run_pipeline_pynq import RingPynqBackend, timing_result


class PipelineEntryTests(unittest.TestCase):
    def test_dma_lookup_distinguishes_repeated_slot_names(self):
        backend = RingPynqBackend.__new__(RingPynqBackend)
        first = SimpleNamespace(physical_address=0x100000, nbytes=4096)
        second = SimpleNamespace(physical_address=0x200000, nbytes=4096)
        backend.allocations = {first.physical_address: first, second.physical_address: second}
        self.assertIs(backend._allocation("fused", Buffer(0x100000, 4096)), first)
        self.assertIs(backend._allocation("fused", Buffer(0x200000, 4096)), second)
        with self.assertRaises(RuntimeError):
            backend._allocation("fused", Buffer(0x100000, 2048))
        with self.assertRaises(RuntimeError):
            backend._allocation("fused", Buffer(0x300000, 4096))

    def test_batch_and_interval_rates_use_different_actual_spans(self):
        result = timing_result(10.0, [10.1, 10.12, 10.14], 10.15)
        self.assertAlmostEqual(result["batch_fps"], 20)
        self.assertAlmostEqual(result["completion_interval_fps"], 50)
        self.assertAlmostEqual(result["max_completion_gap_ms"], 20)
        with self.assertRaises(ValueError):
            timing_result(10.0, [10.1], 10.2)


if __name__ == "__main__":
    unittest.main()
