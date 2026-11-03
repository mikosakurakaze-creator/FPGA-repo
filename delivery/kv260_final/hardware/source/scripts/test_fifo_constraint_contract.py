"""Guard the narrow normalization of compiled XPM reset-constraint ordering."""
import unittest

from audit_fifo_storage_timing import compiled_contract


def reset_block(scope, source_id):
    return [f'set_property SRC_FILE_INFO {{cfile:xpm.tcl rfile:xpm.tcl id:{source_id} order:LATE scoped_inst:{scope} unmanaged:yes rxprname:xpm.tcl}} [current_design]',
            f'set_property src_info {{type:SCOPED_XDC file:{source_id} line:2 export:INPUT save:NONE read:READ}} [current_design]',
            'current_instance -quiet', 'current_instance ' + scope,
            'set_false_path -through [get_ports -scoped_to_current_instance -no_traverse src_arst]',
            'current_instance -quiet']


class ConstraintContractTests(unittest.TestCase):
    def setUp(self):
        self.a = 'system_i/cnn_model_sc/inst/a/m_sc_xpm_cdc_async_rst_inst'
        self.b = 'system_i/cnn_model_sc/inst/b/s_sc_xpm_cdc_async_rst_inst'
        self.original = reset_block(self.a, 1) + reset_block(self.b, 2)

    def test_independent_reset_blocks_can_reorder_and_renumber(self):
        changed = reset_block(self.b, 37) + reset_block(self.a, 56)
        self.assertEqual(compiled_contract(self.original), compiled_contract(changed))

    def test_scope_change_is_rejected(self):
        changed = reset_block(self.a, 1) + reset_block(self.b + '_other', 2)
        self.assertNotEqual(compiled_contract(self.original), compiled_contract(changed))

    def test_missing_reset_cut_is_rejected(self):
        changed = [s for s in self.original if not s.startswith('set_false_path')]
        self.assertNotEqual(compiled_contract(self.original), compiled_contract(changed))

    def test_duplicate_reset_cut_is_rejected(self):
        changed = self.original + reset_block(self.a, 3)
        self.assertNotEqual(compiled_contract(self.original), compiled_contract(changed))

    def test_clock_period_change_is_rejected(self):
        self.assertNotEqual(compiled_contract(self.original + ['create_clock -period 10 [get_ports clk]']),
                            compiled_contract(self.original + ['create_clock -period 20 [get_ports clk]']))

    def test_non_reset_command_order_is_preserved(self):
        commands = ['set_max_delay 5 -from A -to B', 'set_max_delay 6 -from A -to B']
        self.assertNotEqual(compiled_contract(self.original + commands),
                            compiled_contract(self.original + list(reversed(commands))))

    def test_source_line_provenance_is_preserved(self):
        changed = [s.replace(' line:2 ', ' line:3 ') for s in self.original]
        self.assertNotEqual(compiled_contract(self.original), compiled_contract(changed))

    def test_unresolved_source_id_is_rejected(self):
        changed = [s.replace(' file:1 ', ' file:99 ') for s in self.original]
        with self.assertRaises(ValueError):
            compiled_contract(changed)

    def test_routed_reset_blocks_can_reorder_without_source_metadata(self):
        def routed(scope):
            return ['current_instance ' + scope,
                    'set_false_path -through [get_ports -scoped_to_current_instance -no_traverse src_arst]',
                    'current_instance -quiet']
        head = ['create_clock -period 10 [get_ports clk]']
        self.assertEqual(compiled_contract(head + routed(self.a) + routed(self.b)),
                         compiled_contract(head + routed(self.b) + routed(self.a)))

    def test_routed_reset_cut_target_change_is_rejected(self):
        original = ['current_instance ' + self.a,
                    'set_false_path -through [get_ports -scoped_to_current_instance -no_traverse src_arst]']
        changed = [s.replace('src_arst]', 'dest_arst]') for s in original]
        self.assertNotEqual(compiled_contract(original), compiled_contract(changed))


if __name__ == '__main__':
    unittest.main()
