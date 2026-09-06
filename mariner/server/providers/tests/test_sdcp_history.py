import json
import pathlib
import tempfile

from pyexpect import expect
from pyfakefs.fake_filesystem_unittest import TestCase
from pyre_extensions import none_throws

from mariner.server.providers.sdcp.history import HistoryStore, TaskStatus


def _url(task_id: str, filename: str) -> str:
    return f"http://printer/thumbnail/{task_id}"


class HistoryStoreTest(TestCase):
    def setUp(self) -> None:
        self.setUpPyfakefs(additional_skip_names=["importlib.metadata"])
        self.path = pathlib.Path(tempfile.gettempdir()) / "sdcp_history.json"
        self.store = HistoryStore(self.path)

    def _start(self, filename: str, total_layer: int = 0) -> str:
        """start_task is Optional[str]; these tests always expect an id."""
        return none_throws(self.store.start_task(filename, total_layer))

    # -- lifecycle ------------------------------------------------------

    def test_start_task_opens_a_record(self) -> None:
        task_id = self.store.start_task("model.ctb", total_layer=400)
        expect(task_id is not None).to_equal(True)
        expect(self.store.task_ids()).to_equal([task_id])
        expect(self.store.open_task_id()).to_equal(task_id)

    def test_start_task_ignores_empty_filename(self) -> None:
        expect(self.store.start_task("")).to_equal(None)
        expect(self.store.task_ids()).to_equal([])

    def test_restarting_same_file_reuses_the_open_task(self) -> None:
        first = self.store.start_task("model.ctb", 400)
        second = self.store.start_task("model.ctb", 400)
        expect(second).to_equal(first)
        expect(len(self.store.task_ids())).to_equal(1)

    def test_a_different_file_closes_the_previous_task(self) -> None:
        first = self.store.start_task("a.ctb", 100)
        second = self.store.start_task("b.ctb", 200)
        expect(first != second).to_equal(True)
        expect(self.store.open_task_id()).to_equal(second)
        expect(len(self.store.task_ids())).to_equal(2)

    def test_newest_task_is_first(self) -> None:
        self.store.start_task("a.ctb")
        self.store.finish_task(TaskStatus.STOPPED)
        newest = self.store.start_task("b.ctb")
        expect(self.store.task_ids()[0]).to_equal(newest)

    def test_progress_advances_but_never_regresses(self) -> None:
        self.store.start_task("model.ctb", 400)
        self.store.update_progress("model.ctb", 120, 400)
        self.store.update_progress("model.ctb", 50, 400)
        details = self.store.details([], _url)
        expect(details[0]["AlreadyPrintLayer"]).to_equal(120)

    def test_progress_for_a_different_file_is_ignored(self) -> None:
        self.store.start_task("model.ctb", 400)
        self.store.update_progress("other.ctb", 300, 400)
        expect(self.store.details([], _url)[0]["AlreadyPrintLayer"]).to_equal(0)

    # -- completion inference -------------------------------------------

    def test_reaching_the_last_layer_counts_as_completed(self) -> None:
        self.store.start_task("model.ctb", 400)
        self.store.update_progress("model.ctb", 400, 400)
        self.store.finish_task(TaskStatus.STOPPED)
        expect(self.store.details([], _url)[0]["TaskStatus"]).to_equal(
            TaskStatus.COMPLETED
        )

    def test_stopping_early_counts_as_stopped(self) -> None:
        self.store.start_task("model.ctb", 400)
        self.store.update_progress("model.ctb", 120, 400)
        self.store.finish_task(TaskStatus.STOPPED)
        expect(self.store.details([], _url)[0]["TaskStatus"]).to_equal(
            TaskStatus.STOPPED
        )

    def test_finish_without_an_open_task_is_a_noop(self) -> None:
        self.store.finish_task(TaskStatus.STOPPED)
        expect(self.store.task_ids()).to_equal([])

    def test_finished_task_sets_end_time(self) -> None:
        self.store.start_task("model.ctb", 10)
        self.store.finish_task(TaskStatus.STOPPED)
        expect(self.store.open_task_id()).to_equal(None)
        expect(self.store.details([], _url)[0]["EndTime"] > 0).to_equal(True)

    # -- detail rendering -----------------------------------------------

    def test_details_match_the_spec_shape(self) -> None:
        task_id = self._start("model.ctb", 400)
        entry = self.store.details([task_id], _url)[0]
        expect(sorted(entry.keys())).to_equal(
            sorted(
                [
                    "Thumbnail",
                    "TaskName",
                    "BeginTime",
                    "EndTime",
                    "TaskStatus",
                    "SliceInformation",
                    "AlreadyPrintLayer",
                    "TaskId",
                    "MD5",
                    "CurrentLayerTalVolume",
                    "TimeLapseVideoStatus",
                    "TimeLapseVideoUrl",
                    "ErrorStatusReason",
                ]
            )
        )
        expect(entry["TaskName"]).to_equal("model.ctb")
        expect(entry["TaskId"]).to_equal(task_id)
        expect(entry["Thumbnail"]).to_equal(_url(task_id, "model.ctb"))

    def test_details_with_no_ids_returns_everything(self) -> None:
        self.store.start_task("a.ctb")
        self.store.finish_task(TaskStatus.STOPPED)
        self.store.start_task("b.ctb")
        expect(len(self.store.details([], _url))).to_equal(2)

    def test_unknown_ids_are_skipped(self) -> None:
        self.store.start_task("a.ctb")
        expect(self.store.details(["does-not-exist"], _url)).to_equal([])

    def test_thumbnail_can_be_empty(self) -> None:
        task_id = self._start("gone.ctb")
        entry = self.store.details([task_id], lambda _t, _f: "")[0]
        expect(entry["Thumbnail"]).to_equal("")

    def test_callback_receives_the_filename(self) -> None:
        self.store.start_task("model.ctb")
        seen = []
        self.store.details([], lambda task_id, filename: seen.append(filename) or "")
        expect(seen).to_equal(["model.ctb"])

    def test_callback_may_reenter_the_store_without_deadlocking(self) -> None:
        # The real callback checks the file on disk and previously called
        # back into the store, which self-deadlocked on the non-reentrant
        # lock. details() must not hold the lock while calling out.
        task_id = self._start("model.ctb")

        def reentrant(inner_id: str, filename: str) -> str:
            return str(self.store.filename_for(inner_id))

        entry = self.store.details([task_id], reentrant)[0]
        expect(entry["Thumbnail"]).to_equal("model.ctb")

    def test_filename_lookup(self) -> None:
        task_id = self._start("model.ctb")
        expect(self.store.filename_for(task_id)).to_equal("model.ctb")
        expect(self.store.filename_for("nope")).to_equal(None)

    # -- persistence ----------------------------------------------------

    def test_history_survives_a_reload(self) -> None:
        task_id = self._start("model.ctb", 400)
        self.store.update_progress("model.ctb", 42, 400)
        self.store.finish_task(TaskStatus.STOPPED)

        reloaded = HistoryStore(self.path)
        expect(reloaded.task_ids()).to_equal([task_id])
        entry = reloaded.details([task_id], _url)[0]
        expect(entry["AlreadyPrintLayer"]).to_equal(42)
        expect(entry["TaskName"]).to_equal("model.ctb")

    def test_bounded_by_limit(self) -> None:
        store = HistoryStore(self.path, limit=3)
        for i in range(6):
            store.start_task(f"file{i}.ctb")
            store.finish_task(TaskStatus.STOPPED)
        expect(len(store.task_ids())).to_equal(3)

    def test_limit_is_applied_on_reload(self) -> None:
        store = HistoryStore(self.path, limit=10)
        for i in range(5):
            store.start_task(f"file{i}.ctb")
            store.finish_task(TaskStatus.STOPPED)
        expect(len(HistoryStore(self.path, limit=2).task_ids())).to_equal(2)

    def test_corrupt_history_is_discarded_not_fatal(self) -> None:
        self.path.write_text("{not json at all", encoding="utf-8")
        store = HistoryStore(self.path)
        expect(store.task_ids()).to_equal([])
        expect(store.start_task("model.ctb") is not None).to_equal(True)

    def test_records_from_another_version_are_skipped(self) -> None:
        self.path.write_text(
            json.dumps([{"unexpected": "shape"}, "not-an-object"]),
            encoding="utf-8",
        )
        store = HistoryStore(self.path)
        expect(store.task_ids()).to_equal([])

    def test_missing_file_starts_empty(self) -> None:
        store = HistoryStore(pathlib.Path(tempfile.gettempdir()) / "absent.json")
        expect(store.task_ids()).to_equal([])
