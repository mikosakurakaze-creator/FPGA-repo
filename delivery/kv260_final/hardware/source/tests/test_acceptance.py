import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from accept_system import timing_summary, route_summary, critical_rows, ps_clock_proof, PS_CLOCK_PINS, bus_skew_summary


class AcceptanceTests(unittest.TestCase):
    def timing(self, wns="0.123", whs="0.045", no_clock=0):
        return ("WNS(ns) TNS(ns) TNS_Fail TNS_Total WHS(ns) THS(ns) THS_Fail THS_Total WPWS(ns) TPWS(ns)\n"
                "------- ------- -------- --------- ------- ------- -------- --------- -------- --------\n"
                f"{wns} 0.000 0 100 {whs} 0.000 0 100 2.000 0.000\n"
                f"1. checking no_clock ({no_clock})\n2. checking constant_clock (0)\n"
                "4. checking unconstrained_internal_endpoints (0)\n7. checking multiple_clock (0)\n")

    def test_accepts_covered_positive_setup_and_hold(self):
        self.assertEqual(timing_summary(self.timing())["WHS_ns"],0.045)

    def test_rejects_negative_hold_or_setup(self):
        for wns,whs in (("-0.001","0.1"),("0.1","-0.001")):
            with self.assertRaises(ValueError):timing_summary(self.timing(wns,whs))

    def test_rejects_unclocked_registers(self):
        with self.assertRaises(ValueError):timing_summary(self.timing(no_clock=8))

    def test_rejects_missing_coverage(self):
        with self.assertRaises(ValueError):timing_summary(self.timing().split("1. checking")[0])

    def unused_ps(self):
        pins=sorted(PS_CLOCK_PINS)
        proof="\n".join("PIN "+pin+" REF=PS8 DIR=OUT INPUT_LOADS=0 TOP_PORTS=0 CLOCKS=0 NETS=dangling" for pin in pins)
        proof+="\nCHECKED_UNUSED_PS_OUTPUTS=8\n"
        report="There are 8 register/latch pins with no clock (HIGH)\n\n"+"\n".join(pins)+"\n\n2. checking constant_clock (0)\n"
        return proof,report

    def test_accepts_only_proven_unloaded_ps_outputs(self):
        proof,report=self.unused_ps()
        result=timing_summary(self.timing(no_clock=8),ps_clock_proof(proof,report))
        self.assertEqual(result["coverage"]["no_clock"],8)
        self.assertEqual(result["coverage"]["active_unclocked_pins"],0)

    def test_preserves_raw_zero_with_separate_eight_pin_audit(self):
        proof,report=self.unused_ps()
        result=timing_summary(self.timing(no_clock=0),ps_clock_proof(proof,report))
        self.assertEqual(result["coverage"]["no_clock"],0)
        self.assertEqual(result["coverage"]["classified_unused_ps_no_clock_outputs"],0)
        self.assertEqual(result["coverage"]["verified_unloaded_ps_clock_outputs"],8)

    def test_rejects_ps_outputs_with_loads_or_top_ports(self):
        proof,report=self.unused_ps()
        for field in ("INPUT_LOADS","TOP_PORTS","CLOCKS"):
            with self.assertRaises(ValueError):ps_clock_proof(proof.replace(field+"=0",field+"=1",1),report)

    def test_rejects_unknown_unclocked_pin(self):
        proof,report=self.unused_ps()
        with self.assertRaises(ValueError):ps_clock_proof(proof,report.replace(sorted(PS_CLOCK_PINS)[0],"system_i/active_ff/C"))

    def test_rejects_incomplete_unused_ps_proof(self):
        proof,report=self.unused_ps()
        with self.assertRaises(ValueError):ps_clock_proof("\n".join(proof.splitlines()[1:]),report)

    def test_requires_all_nets_routed(self):
        def report(fully):
            return f"# of routable nets......... : 100\n# of fully routed nets..... : {fully}\n# of nets with routing errors... : 0\n"
        self.assertEqual(route_summary(report(100))["fully routed nets"],100)
        with self.assertRaises(ValueError):route_summary(report(99))

    def test_rejects_critical_cdc_but_allows_zero_summary(self):
        self.assertEqual(critical_rows("| CDC-1 | Critical | 0 | Single bit unknown |",{"critical"}),[])
        self.assertTrue(critical_rows("| CDC-1 | Critical | 1 | Single bit unknown |",{"critical"}))

    def test_rejects_drc_error(self):
        self.assertTrue(critical_rows("| NSTD-1 | Error | 1 | Unspecified I/O Standard |",{"error"}))

    def test_rejects_actual_whitespace_cdc_critical_summary(self):
        self.assertTrue(critical_rows("CDC-1 Critical 1 1-bit unknown CDC circuitry",{"critical"}))
        self.assertEqual(critical_rows("CDC-1 Critical 0 1-bit unknown CDC circuitry",{"critical"}),[])

    def test_rejects_actual_whitespace_cdc_critical_detail(self):
        self.assertTrue(critical_rows("1 CDC-1 Critical 1-bit unknown CDC circuitry 0 False Path source target",{"critical"}))

    def test_accepts_actual_whitespace_cdc_info_and_warning(self):
        self.assertEqual(critical_rows("CDC-3 Info 20 1-bit synchronized\nCDC-15 Warning 471 Clock enable controlled",{"critical","error"}),[])

    def skew(self,slack="4.400"):
        return ("1. Bus Skew Report Summary\n--------------------------\n"
                "Id Position From To Corner Requirement(ns) Actual(ns) Slack(ns)\n"
                "1 285 [get_cells {source}]\n  [get_cells {target}]\n"
                f"  Slow 5.000 0.600 {slack}\n"
                "2. Bus Skew Report Per Constraint\n---------------------------------\n")

    def test_accepts_bus_skew_constraints(self):
        self.assertEqual(bus_skew_summary(self.skew()),{"constraints":1,"worst_slack_ns":4.4,"violations":0})

    def test_rejects_bus_skew_violation(self):
        with self.assertRaises(ValueError):bus_skew_summary(self.skew("-0.001"))

    def test_rejects_missing_bus_skew_summary(self):
        with self.assertRaises(ValueError):bus_skew_summary("No constraints found")

    def test_rejects_incomplete_bus_skew_coverage(self):
        with self.assertRaises(ValueError):bus_skew_summary(self.skew().replace("1 285","2 285"))


if __name__=="__main__":unittest.main()
