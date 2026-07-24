"""Tests for shared command helpers (atomic writes, encryption guard, field walks)."""

import os

import pytest
import typer

from pdf_tool.commands import common
from pdf_tool.commands.common import (
    atomic_output,
    ensure_not_encrypted,
    resolve_inherited,
    walk_field_chain,
)


class FakeNode(dict):
    """Minimal stand-in for a pypdf dictionary object."""

    def get_object(self):
        return self


class TestAtomicOutput:
    def test_writes_target_on_success(self, tmp_path):
        target = tmp_path / "out.bin"
        with atomic_output(target) as tmp:
            tmp.write_bytes(b"payload")
        assert target.read_bytes() == b"payload"
        assert list(tmp_path.glob(".out.bin.*")) == []  # no temp leftovers

    def test_failure_keeps_original_and_cleans_temp(self, tmp_path):
        target = tmp_path / "out.bin"
        target.write_bytes(b"original")
        with pytest.raises(RuntimeError), atomic_output(target) as tmp:
            tmp.write_bytes(b"half-written garbage")
            raise RuntimeError("writer blew up")
        assert target.read_bytes() == b"original"  # untouched
        assert list(tmp_path.glob(".out.bin.*")) == []

    def test_in_place_overwrite(self, tmp_path):
        target = tmp_path / "doc.pdf"
        target.write_bytes(b"old content")
        with atomic_output(target) as tmp:
            # consumer may read the ORIGINAL while writing the temp
            assert target.read_bytes() == b"old content"
            tmp.write_bytes(b"new content")
        assert target.read_bytes() == b"new content"

    @pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits")
    def test_preserves_existing_permissions(self, tmp_path):
        target = tmp_path / "doc.pdf"
        target.write_bytes(b"old")
        target.chmod(0o640)
        with atomic_output(target) as tmp:
            tmp.write_bytes(b"new")
        assert target.stat().st_mode & 0o777 == 0o640


class TestEnsureNotEncrypted:
    def test_encrypted_pdf_exits(self, encrypted_pdf):
        with pytest.raises(typer.Exit) as excinfo:
            ensure_not_encrypted(encrypted_pdf)
        assert excinfo.value.exit_code == 1

    def test_plain_pdf_passes(self, simple_pdf):
        ensure_not_encrypted(simple_pdf)  # no raise

    def test_non_pdf_is_left_to_command(self, tmp_path):
        bogus = tmp_path / "not_a_pdf.pdf"
        bogus.write_bytes(b"hello")
        ensure_not_encrypted(bogus)  # no raise — command's own handling reports


class TestResourceLimits:
    def test_input_size_limit(self, tmp_path, monkeypatch):
        path = tmp_path / "large.pdf"
        path.write_bytes(b"%PDF-too-large")
        monkeypatch.setattr(common, "MAX_INPUT_BYTES", 4)

        with pytest.raises(typer.Exit) as excinfo:
            common.ensure_input_size(path)

        assert excinfo.value.exit_code == 2

    def test_json_size_limit(self, monkeypatch):
        monkeypatch.setattr(common, "MAX_JSON_INPUT_BYTES", 4)

        with pytest.raises(typer.Exit) as excinfo:
            common.ensure_json_size("12345")

        assert excinfo.value.exit_code == 2


class TestWalkFieldChain:
    def test_yields_chain_in_order(self):
        root = FakeNode({"/T": "root"})
        child = FakeNode({"/T": "child", "/Parent": root})
        assert [n["/T"] for n in walk_field_chain(child)] == ["child", "root"]

    def test_parent_cycle_terminates(self):
        a = FakeNode({"/T": "a"})
        b = FakeNode({"/T": "b", "/Parent": a})
        a["/Parent"] = b  # cycle a <-> b
        names = [n["/T"] for n in walk_field_chain(a)]
        assert names == ["a", "b"]

    def test_self_parent_terminates(self):
        a = FakeNode({"/T": "a"})
        a["/Parent"] = a
        assert [n["/T"] for n in walk_field_chain(a)] == ["a"]


class TestResolveInherited:
    def test_finds_value_on_parent(self):
        root = FakeNode({"/V": "inherited"})
        child = FakeNode({"/Parent": root})
        assert resolve_inherited(child, "/V") == "inherited"

    def test_returns_none_on_cycle_without_key(self):
        a = FakeNode()
        b = FakeNode({"/Parent": a})
        a["/Parent"] = b
        assert resolve_inherited(a, "/V") is None
