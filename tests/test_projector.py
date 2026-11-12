"""Fixed-point accuracy, signed32 bounds and native-kernel contract checks."""
from array import array
import ast
import importlib.util
import math
import operator
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    # The production cosmos module now uses its sibling .projector; give this
    # isolated fixture a real package path without importing the badge app.
    spec = importlib.util.spec_from_file_location(name, ROOT / filename,
                                                submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p = load("projector_under_test", "projector.py")
cosmos = load("projector_float_reference", "fx_cosmos.py")


def emitted(output, counts):
    return [(bucket, tuple(output[bucket * p.STRIDE + index * 3:
                                  bucket * p.STRIDE + index * 3 + 3]))
            for bucket in range(6) for index in range(counts[bucket])]


def buffers(n=1):
    source = p.pack_points([(0, 0, 1, 0)] * n)
    output = array("i", [-987654321] * (p.OUTPUT_SIZE + 17))
    counts = array("i", [99] * 6)
    params = array("i", [n, 1, p.Q, 0, p.Q, 0, 1120, 17, -64])
    return source, output, counts, params


class ProjectorTests(unittest.TestCase):
    def test_q15_matches_float_sphere_within_one_pixel(self):
        """Compare every original sphere point across rotation and both LODs."""
        maximum_error = 0
        compared = 0
        ct, st = math.cos(.34), math.sin(.34)
        for point in cosmos._SPHERE:
            projector = p.Projector([point])
            x, y, z, material = point
            for angle in range(0, 256, 13):
                c, s = math.cos(angle * math.tau / 256), math.sin(angle * math.tau / 256)
                rx, rz = x * c + z * s, z * c - x * s
                ry, rz = y * ct - rz * st, y * st + rz * ct
                for detail in (True, False):
                    output, counts = projector.project(c, s, ct, st, 96, detail)
                    actual = emitted(output, counts)
                    if abs(rz - 1 / 3.4) <= .0002:
                        # Quantization may move a sample across the tangent.
                        continue
                    if rz <= 1 / 3.4:
                        self.assertEqual(actual, [])
                        continue
                    self.assertEqual(len(actual), 1)
                    scale = 96 * math.sqrt(3.4 * 3.4 - 1) / (3.4 - rz)
                    size = 1.25 + rz * (1.05 if detail else 1.4)
                    expected = (rx * scale - size / 2, ry * scale - 4 - size / 2, size)
                    for fixed, floating in zip(actual[0][1], expected):
                        error = abs(fixed / 16 - floating)
                        maximum_error = max(maximum_error, error)
                        self.assertLessEqual(error, 1)
                    light = rx * -.48 + ry * -.35 + rz * .8
                    if abs(light - .48) > .0002:
                        self.assertEqual(actual[0][0], material * 2 + int(light > .48))
                    compared += 1
        self.assertGreater(compared, 4000)
        self.assertLess(maximum_error, .3)

    def test_maximum_bucket_and_detail_stride_do_not_write_beyond_output(self):
        source, output, counts, params = buffers(308)
        for step, expected in ((1, 308), (2, 154)):
            params[1] = step
            returned = p.project(source, output, counts, params)
            self.assertIs(returned[0], output)
            self.assertIs(returned[1], counts)
            self.assertEqual(list(counts), [0, expected, 0, 0, 0, 0])
            self.assertEqual(list(output[p.OUTPUT_SIZE:]), [-987654321] * 17)
        self.assertEqual(p.STRIDE, 308 * 3)
        self.assertEqual(p.OUTPUT_SIZE, 6 * 308 * 3)

    def test_reuses_source_and_all_output_buffers(self):
        projector = p.Projector(cosmos._SPHERE)
        identities = tuple(map(id, (projector.source, projector.output, projector.counts, projector.params)))
        for angle in range(20):
            projector.project(math.cos(angle), math.sin(angle), 1, 0, 70, bool(angle % 2))
            self.assertEqual(tuple(map(id, (projector.source, projector.output, projector.counts, projector.params))), identities)

    def test_invalid_scalar_params_are_rejected_before_any_output_write(self):
        invalid = ((0, -1), (0, 309), (1, 0), (1, 3), (2, p.Q + 1),
                   (4, -p.Q - 1), (6, 0), (6, 1537), (7, 16), (8, 1921))
        for index, value in invalid:
            source, output, counts, params = buffers()
            params[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                p.project(source, output, counts, params)
            self.assertEqual(list(counts), [99] * 6)
            self.assertTrue(all(value == -987654321 for value in output))
        source, output, counts, params = buffers()
        params[2:4] = array("i", [p.Q, p.Q])
        with self.assertRaises(ValueError):
            p.project(source, output, counts, params)

    def test_wrong_type_width_short_buffers_and_aliases_are_rejected(self):
        good = buffers()
        for index in range(4):
            for wrong in ([], bytearray(100), array("I", [0] * len(good[index])),
                          array("h", [0] * len(good[index])), array("i")):
                args = list(good)
                args[index] = wrong
                with self.subTest(index=index, wrong_type=type(wrong)), self.assertRaises(ValueError):
                    p.project(*args)
        shared = array("i", [1, 1, p.Q, 0, p.Q, 0, 1120, 17, -64] + [0] * p.OUTPUT_SIZE)
        for first, second in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)):
            args = list(buffers())
            args[first] = args[second] = shared
            with self.subTest(alias=(first, second)), self.assertRaises(ValueError):
                p.project(*args)

    def test_corrupt_source_records_are_skipped_inside_kernel(self):
        source, output, counts, params = buffers()
        for record in ((2147483647, 0, p.Q, 0), (-2147483648, 0, 0, 0),
                       (p.Q, p.Q, p.Q, 0), (0, 0, 10000, 0),
                       (0, 0, p.Q, -1), (0, 0, p.Q, 3)):
            source[:] = array("i", record)
            p.project(source, output, counts, params)
            self.assertEqual(list(counts), [0] * 6)
            self.assertTrue(all(value == -987654321 for value in output))

    def test_invalid_setup_and_nonfinite_inputs_fail_closed(self):
        for point in ((0, 0, 0, 0), (1, 1, 1, 0), (0, 0, 1, 3),
                      (0, 0, 1, True), (float("nan"), 0, 1, 0), (0, 0, float("inf"), 0)):
            with self.subTest(point=point), self.assertRaises(ValueError):
                p.Projector([point])
        with self.assertRaises(ValueError):
            p.Projector([(0, 0, 1, 0)] * 309)
        projector = p.Projector([])
        output, counts = projector.project(1, 0, 1, 0, 70)
        self.assertEqual(sum(counts), 0)
        for invalid in (float("nan"), float("inf"), True, None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                projector.project(invalid, 0, 1, 0, 70)

    def test_viper_body_has_only_four_typed_buffer_args_and_matches_reference(self):
        """Execute the exact Viper body as Python too; hardware compile is separate."""
        tree = ast.parse((ROOT / "projector.py").read_text())
        functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_project_viper"]
        self.assertEqual(len(functions), 1)
        kernel = functions[0]
        self.assertEqual([argument.annotation.id for argument in kernel.args.args], ["ptr32"] * 4)
        self.assertEqual(len(kernel.args.args), 4)
        kernel.decorator_list = []
        for argument in kernel.args.args:
            argument.annotation = None
        namespace = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[kernel], type_ignores=[])), "viper-body", "exec"), namespace)
        original = p.Projector(cosmos._SPHERE)
        duplicate = p.Projector(cosmos._SPHERE)
        for index in range(32):
            angle = index * math.tau / 32
            original.project(math.cos(angle), math.sin(angle), math.cos(.34), math.sin(.34), 72, bool(index % 2))
            duplicate.params[:] = original.params
            namespace["_project_viper"](duplicate.source, duplicate.output, duplicate.counts, duplicate.params)
            self.assertEqual(list(original.counts), list(duplicate.counts))
            self.assertEqual(emitted(original.output, original.counts), emitted(duplicate.output, duplicate.counts))

    def test_every_kernel_arithmetic_intermediate_fits_signed32(self):
        """Exercise the native body with checked32-bit arithmetic, not bigints."""
        class CheckedArithmetic(ast.NodeTransformer):
            def visit_BinOp(self, node):
                self.generic_visit(node)
                return ast.copy_location(ast.Call(func=ast.Name(id="checked", ctx=ast.Load()),
                                                  args=[ast.Constant(type(node.op).__name__), node.left, node.right],
                                                  keywords=[]), node)

        operations = {"Add": operator.add, "Sub": operator.sub, "Mult": operator.mul,
                      "FloorDiv": operator.floordiv, "RShift": operator.rshift}

        def checked(operation, first, second):
            result = operations[operation](first, second)
            self.assertGreaterEqual(result, -2147483648)
            self.assertLessEqual(result, 2147483647)
            return result

        tree = ast.parse((ROOT / "projector.py").read_text())
        kernel = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_project_viper")
        kernel.decorator_list = []
        for argument in kernel.args.args:
            argument.annotation = None
        namespace = {"checked": checked}
        code = CheckedArithmetic().visit(ast.Module(body=[kernel], type_ignores=[]))
        exec(compile(ast.fix_missing_locations(code), "checked-viper-body", "exec"), namespace)
        axes = [(1, 0, 0, 0), (-1, 0, 0, 1), (0, 1, 0, 2),
                (0, -1, 0, 0), (0, 0, 1, 1), (0, 0, -1, 2)]
        projector = p.Projector(list(cosmos._SPHERE[:300]) + axes)
        for yaw in range(0, 256, 32):
            for tilt in range(0, 256, 32):
                angle, lean = yaw * math.tau / 256, tilt * math.tau / 256
                projector.project(math.cos(angle), math.sin(angle), math.cos(lean), math.sin(lean), 96, False)
                namespace["_project_viper"](projector.source, projector.output, projector.counts, projector.params)


if __name__ == "__main__":
    unittest.main()
