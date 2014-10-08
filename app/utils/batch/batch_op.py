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

"""Batch operation classes."""

import pymongo

from handlers.count import (
    VALID_KEYS as COUNT_VALID_KEYS,
    count_all_collections,
    count_one_collection,
)
from models import (
    DB_NAME,
    OP_ID_KEY,
    RESULT_KEY,
)


class BatchOperation(object):
    """The base batch operation that can be performed.

    Specialized operations, for count or other collections, should be created
    starting from this class.
    """

    # TODO: need to pass database parameters.

    def __init__(self, collection, operation_id=None):
        """Create a new `BatchOperation`.

        :param collection: The db collection where to perform the operation.
        :type collection: string
        :param operation_id: Optional name for this operation.
        :type operation_id: string
        """
        # The database connection to perform operation on. Restrict the pool
        # size since it is only used for one operation.
        self._database = pymongo.MongoClient(max_pool_size=3)[DB_NAME]
        self._operation_id = operation_id
        self._collection = collection
        self._operation = None
        self.args = []
        self.kwargs = {}
        self.query_args = {}
        self.valid_keys = None
        self.document_id = None
        self.method = None
        self.query_args_func = None

    @property
    def collection(self):
        """Get the name of the db collection."""
        return self._collection

    @collection.setter
    def collection(self, value):
        """Set the name of the db collection.

        :param value: The name of the collection to set.
        :type value: string
        """
        self._collection = value

    @property
    def operation(self):
        """Get the (real) operation associated with this batch op.

        It should be a function that will be called when invoking `run()` and
        it should accept `*args` and `**kwargs` parameters.
        """
        return self._operation

    @operation.setter
    def operation(self, value):
        """Set the operation to be performed when invoking `run()`.

        :param value: The operation to set.
        :type value: function
        """
        self._operation = value

    @property
    def operation_id(self):
        """Get the ID of this batch operation.

        The operation ID is a name associated with this batch operation. If
        provided it will be returned in the response.

        Useful to differentiate between multiple operations in a single batch.
        """
        return self._operation_id

    @operation_id.setter
    def operation_id(self, value):
        """Set the operation ID value.

        :param value: The operation ID to set.
        :param value: string
        """
        self._operation_id = value

    def prepare_operation(self):
        """Prepare the operation that needs to be performed.

        This method is automatically called when invoking `run()` to make sure
        all necessary parameters are set up correctly.

        Subclasses should not override this method, but instead override the
        private ones specialized for each HTTP verbs.
        """
        if self.method == "GET":
            self._prepare_get_operation()
        elif self.method == "DELETE":
            self._prepare_delete_operation()
        elif self.method == "POST":
            self._prepare_post_operation()

    def _prepare_get_operation(self):
        """Prepare the necessary parameters for a GET operation."""
        raise NotImplementedError

    def _prepare_post_operation(self):
        """Prepare the necessary parameters for a POST operation."""
        raise NotImplementedError

    def _prepare_delete_operation(self):
        """Prepare the necessary parameters for a DELETE operation."""
        raise NotImplementedError

    def _prepare_response(self, result):
        """Prepare the response to be returned.

        :param result: The result obtained after invoking the `operation`.
        :return A dictionary
        """
        response = {}
        if self._operation_id:
            response[OP_ID_KEY] = self._operation_id
        response[RESULT_KEY] = result

        return response

    def run(self):
        """Prepare and run this operation.

        This method will invoke the `operation` attribute as a function, passing
        the defined `args` and `kwargs` parameters.
        """
        self.prepare_operation()

        result = []
        if self.operation:
            result = self.operation(*self.args, **self.kwargs)
        return self._prepare_response(result)


class BatchCountOperation(BatchOperation):
    """The batch operation to perform execute queries on the `count` collection.

    This sublcass is used to execute special queries for the `count` collection.
    """

    def __init__(self, collection, operation_id=None):
        super(BatchCountOperation, self).__init__(collection, operation_id)
        self.valid_keys = COUNT_VALID_KEYS

    def _prepare_get_operation(self):
        if self.document_id:
            self.operation = count_one_collection
            self.args = [
                self._database[self.document_id],
                self.document_id,
                self.query_args_func,
                self.valid_keys.get(self.method)
            ]
        else:
            self.operation = count_all_collections
            self.args = [
                self._database,
                self.query_args_func,
                self.valid_keys.get(self.method)
            ]