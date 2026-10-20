"""Тесты чтения метаданных экземпляров Prism."""

import json
import tempfile
import unittest
from pathlib import Path

from launchers.prism.instance_parser import parse_instance, scan_instances


class InstanceParserTests(unittest.TestCase):
    """Проверяет определение версии Minecraft и загрузчика."""

    def test_parse_fabric_instance(self) -> None:
        """Распознаёт Fabric и версию Minecraft."""
        with tempfile.TemporaryDirectory() as temp_dir:
            instance_dir = Path(temp_dir) / "Fabric test"
            instance_dir.mkdir()
            (instance_dir / "instance.cfg").write_text(
                "InstanceType=OneSix\nname=Fabric test\nInstanceID=fabric-test\n",
                encoding="utf-8",
            )
            pack = {
                "components": [
                    {"uid": "net.minecraft", "version": "1.21.1"},
                    {"uid": "net.fabricmc.fabric-loader", "version": "0.16.5"},
                ]
            }
            (instance_dir / "mmc-pack.json").write_text(
                json.dumps(pack), encoding="utf-8"
            )

            instance = parse_instance(instance_dir)

            self.assertEqual(instance.minecraft_version, "1.21.1")
            self.assertEqual(instance.loader, "Fabric")
            self.assertEqual(instance.loader_version, "0.16.5")
            self.assertEqual(instance.name, "Fabric test")
            self.assertEqual(instance.instance_id, "Fabric test")

    def test_scan_ignores_unrelated_directory(self) -> None:
        """Не считает произвольную папку экземпляром Prism."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "instances").mkdir()
            (root / "instances" / "unrelated").mkdir()

            self.assertEqual(scan_instances(root), [])


if __name__ == "__main__":
    unittest.main()
