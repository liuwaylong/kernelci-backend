# Copyright (C) 2014 Linaro Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Container for all the boot import related functions."""

import glob
import json
import os
import pymongo

from bson import tz_util
from datetime import (
    datetime,
    timedelta
)

from models import (
    BOOT_LOG_KEY,
    DB_NAME,
    DTB_ADDR_KEY,
    DTB_KEY,
    INITRD_ADDR_KEY,
    JOB_KEY,
    KERNEL_IMAGE_KEY,
    KERNEL_KEY,
    UNKNOWN_STATUS,
)
from models.boot import BootDocument
from utils import (
    BASE_PATH,
    LOG,
    is_hidden,
)
from utils.db import save

# Pattern used for glob matching files on the filesystem.
BOOT_REPORT_PATTERN = 'boot-*.json'

# Keys defined only for the boot report JSON format. We store them differently.
BOOT_TIME_JSON = 'boot_time'
LOAD_ADDR_JSON = 'loadaddr'
BOOT_RESULT_JSON = 'boot_result'
BOOT_WARNINGS_JSON = 'boot_warnings'


def import_and_save_boot(json_obj, base_path=BASE_PATH):
    """Wrapper function to be used as an external task.

    This function should only be called by Celery or other task managers.
    Import and save the boot report as found from the parameters in the
    provided JSON object.

    :param json_obj: The JSON object with the values that identify the boot
        report log.
    :param base_path: The base path where to start looking for the boot log
        file. It defaults to: /var/www/images/kernel-ci.
    """
    database = pymongo.MongoClient()[DB_NAME]

    docs = parse_boot_from_json(json_obj, base_path)

    if docs:
        try:
            save(database, docs)
        finally:
            database.connection.disconnect()
    else:
        LOG.info("No boot log imported")


def parse_boot_from_json(json_obj, base_path=BASE_PATH):
    """Parse boot log file from a JSON object.

    The provided JSON object, a dict-like object, should contain at least the
    `job` and `kernel` keys.

    :param json_obj: A dict-like object that should contain the keys `job` and
    :param base_path: The base path where to start looking for the boot log
        file. It defaults to: /var/www/images/kernel-ci.
    :return A list with all the `BootDocument`s.
    """
    job = json_obj[JOB_KEY]
    kernel = json_obj[KERNEL_KEY]

    return _parse_boot(job, kernel, base_path)


def _parse_boot(job, kernel, base_path=BASE_PATH):
    """Traverse the kernel directory and look for boot report logs.

    :param job: The name of the job.
    :param kernel: The name of the kernel.
    :param base_path: The base path where to start traversing.
    :return A list of documents to be saved, or an empty list.
    """
    docs = []

    job_dir = os.path.join(base_path, job)

    if not is_hidden(job) and os.path.isdir(job_dir):
        kernel_dir = os.path.join(job_dir, kernel)

        if not is_hidden(kernel) and os.path.isdir(kernel_dir):
            for defconfig in os.listdir(kernel_dir):
                defconfig_dir = os.path.join(kernel_dir, defconfig)

                if not is_hidden(defconfig) and os.path.isdir(defconfig_dir):
                    docs.extend([
                        _parse_boot_log(boot_log, job, kernel, defconfig)
                        for boot_log in glob.iglob(
                            os.path.join(defconfig_dir, BOOT_REPORT_PATTERN)
                        )
                        if os.path.isfile(boot_log)
                    ])

    return docs


def _parse_boot_log(boot_log, job, kernel, defconfig):
    """Read and parse the actual boot report.

    :param boot_log: The path to the boot report.
    :param job: The name of the job.
    :param kernel: The name of the kernel.
    :param defconfig: The name of the defconfig.
    :return A `BootDocument` object.
    """

    LOG.info("Parsing boot log %s", boot_log)

    boot_json = None
    boot_doc = None

    created = datetime.fromtimestamp(
        os.stat(boot_log).st_mtime, tz=tz_util.utc
    )

    board = os.path.basename(boot_log).\
        replace('boot-', '').replace('.json', '')

    with open(boot_log) as read_f:
        boot_json = json.load(read_f)

    if boot_json:
        boot_doc = BootDocument(board, job, kernel, defconfig)
        boot_doc.created_on = created

        time_d = timedelta(seconds=float(boot_json.get(BOOT_TIME_JSON, 0.0)))
        boot_time = datetime(
            1970, 1, 1,
            minute=time_d.seconds / 60,
            second=time_d.seconds % 60,
            microsecond=time_d.microseconds
        )

        boot_doc.time = boot_time
        boot_doc.status = boot_json.get(BOOT_RESULT_JSON, UNKNOWN_STATUS)
        boot_doc.warnings = boot_json.get(BOOT_WARNINGS_JSON, "0")
        boot_doc.boot_log = boot_json.get(BOOT_LOG_KEY, None)
        boot_doc.initrd_addr = boot_json.get(INITRD_ADDR_KEY, None)
        boot_doc.load_addr = boot_json.get(LOAD_ADDR_JSON, None)
        boot_doc.kernel_image = boot_json.get(KERNEL_IMAGE_KEY, None)
        boot_doc.dtb_addr = boot_json.get(DTB_ADDR_KEY, None)
        boot_doc.dtb = boot_json.get(DTB_KEY, None)

    return boot_doc


def _import_all(base_path=BASE_PATH):
    """Handy function to import all boot logs."""
    boot_docs = []

    for job in os.listdir(base_path):
        job_dir = os.path.join(base_path, job)

        for kernel in os.listdir(job_dir):
            boot_docs.extend(_parse_boot(job, kernel, base_path))

    return boot_docs


if __name__ == '__main__':
    connection = pymongo.MongoClient()
    database = connection[DB_NAME]

    all_docs = _import_all()
    save(database, all_docs)

    connection.disconnect()