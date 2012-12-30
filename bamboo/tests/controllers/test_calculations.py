from time import sleep

import simplejson as json

from bamboo.controllers.abstract_controller import AbstractController
from bamboo.controllers.calculations import Calculations
from bamboo.controllers.datasets import Datasets
from bamboo.core.frame import DATASET_ID
from bamboo.lib.io import create_dataset_from_url
from bamboo.models.calculation import Calculation
from bamboo.models.dataset import Dataset
from bamboo.tests.decorators import requires_async
from bamboo.tests.test_base import TestBase
from bamboo.tests.controllers.test_abstract_datasets import\
    TestAbstractDatasets


class TestCalculations(TestBase):

    def setUp(self):
        TestBase.setUp(self)
        self.controller = Calculations()
        self.dataset_id = None
        self.formula = 'amount + gps_alt'
        self.name = 'test'

    def _post_formula(self, formula=None, name=None):
        if not formula:
            formula = self.formula
        if not name:
            name = self.name

        if not self.dataset_id:
            self.dataset_id = self._post_file()

        return self.controller.create(self.dataset_id, formula, name)

    def _test_error(self, response, error_text=None):
        response = json.loads(response)

        self.assertTrue(isinstance(response, dict))
        self.assertTrue(self.controller.ERROR in response)

        if not error_text:
            error_text = 'Must provide'

        self.assertTrue(error_text in response[self.controller.ERROR])

    def _test_create_from_json(self, json_filename, non_agg_cols=1, group=None,
                               ex_len=1):
        json_filepath = 'tests/fixtures/%s' % json_filename
        mock_uploaded_file = self._file_mock(json_filepath)
        dataset = Dataset.find_one(self.dataset_id)
        prev_columns = len(dataset.dframe().columns)
        response = json.loads(self.controller.create(
            self.dataset_id, json_file=mock_uploaded_file, group=group))

        self.assertTrue(isinstance(response, dict))
        self.assertTrue(self.controller.SUCCESS in response)
        self.assertTrue(self.dataset_id in response[self.controller.SUCCESS])

        self.assertEqual(
            ex_len, len(json.loads(self.controller.show(self.dataset_id))))
        self.assertEqual(
            prev_columns + non_agg_cols,
            len(dataset.reload().dframe().columns))

        return dataset

    def test_show(self):
        self._post_formula()
        response = self.controller.show(self.dataset_id)

        self.assertTrue(isinstance(json.loads(response), list))

    def test_create(self):
        response = json.loads(self._post_formula())

        self.assertTrue(isinstance(response, dict))
        self.assertTrue(self.controller.SUCCESS in response)
        self.assertTrue(self.dataset_id in response[self.controller.SUCCESS])

        dataset = Dataset.find_one(self.dataset_id)

        self.assertEqual(TestAbstractDatasets.NUM_ROWS, len(dataset.dframe()))

    @requires_async
    def test_create_async_not_ready(self):
        self.dataset_id = create_dataset_from_url(
            '%s%s' % (self._local_fixture_prefix(), 'good_eats_huge.csv'),
            allow_local_file=True).dataset_id
        response = json.loads(self._post_formula())
        dataset = Dataset.find_one(self.dataset_id)

        self.assertFalse(dataset.is_ready)
        self.assertTrue(isinstance(response, dict))
        self.assertFalse(DATASET_ID in response)

        while True:
            dataset = Dataset.find_one(self.dataset_id)
            if dataset.is_ready:
                break
            sleep(self.SLEEP_DELAY)

        self.assertFalse(self.name in dataset.schema.keys())

    @requires_async
    def test_create_async_sets_calculation_status(self):
        self.dataset_id = create_dataset_from_url(
            '%s%s' % (self._local_fixture_prefix(), 'good_eats_huge.csv'),
            allow_local_file=True).dataset_id

        while True:
            dataset = Dataset.find_one(self.dataset_id)
            if dataset.is_ready:
                break
            sleep(self.SLEEP_DELAY)

        response = json.loads(self._post_formula())

        self.assertTrue(isinstance(response, dict))
        self.assertTrue(self.controller.SUCCESS in response)
        self.assertTrue(self.dataset_id in response[self.controller.SUCCESS])

        response = json.loads(self.controller.show(self.dataset_id))[0]

        self.assertTrue(isinstance(response, dict))
        self.assertTrue(Calculation.STATE in response)
        self.assertEqual(response[Calculation.STATE],
                         Calculation.STATE_PENDING)
        while True:
            response = json.loads(self.controller.show(self.dataset_id))[0]
            dataset = Dataset.find_one(self.dataset_id)
            if response[Calculation.STATE] != Calculation.STATE_PENDING:
                break
            sleep(self.SLEEP_DELAY)

        self.assertEqual(response[Calculation.STATE],
                         Calculation.STATE_READY)

        dataset = Dataset.find_one(self.dataset_id)

        self.assertTrue(self.name in dataset.schema.keys())

    @requires_async
    def test_create_async(self):
        self.dataset_id = self._post_file()

        while True:
            dataset = Dataset.find_one(self.dataset_id)
            if dataset.is_ready:
                break
            sleep(self.SLEEP_DELAY)

        response = json.loads(self._post_formula())

        self.assertTrue(isinstance(response, dict))
        self.assertTrue(self.controller.SUCCESS in response)
        self.assertTrue(self.dataset_id in response[self.controller.SUCCESS])

        while True:
            response = json.loads(self.controller.show(self.dataset_id))[0]
            dataset = Dataset.find_one(self.dataset_id)
            if response[Calculation.STATE] != Calculation.STATE_PENDING:
                break
            sleep(self.SLEEP_DELAY)

        dataset = Dataset.find_one(self.dataset_id)

        self.assertTrue(self.name in dataset.schema.keys())

        dataset = Dataset.find_one(self.dataset_id)

        self.assertEqual(TestAbstractDatasets.NUM_ROWS, len(dataset.dframe()))

    def test_create_invalid_formula(self):
        dataset_id = self._post_file()
        result = json.loads(
            self.controller.create(dataset_id, '=NON_EXIST', self.name))

        self.assertTrue(isinstance(result, dict))
        self.assertTrue(Datasets.ERROR in result.keys())

    def test_create_remove_summary(self):
        dataset_id = self._post_file()
        Datasets().summary(
            self.dataset_id,
            select=Datasets.SELECT_ALL_FOR_SUMMARY)
        dataset = Dataset.find_one(dataset_id)

        self.assertTrue(isinstance(dataset.stats, dict))
        self.assertTrue(isinstance(dataset.stats[Dataset.ALL], dict))

        self._post_formula()
        # stats should have new column for calculation
        dataset = Dataset.find_one(self.dataset_id)

        self.assertTrue(self.name in dataset.stats.get(Dataset.ALL).keys())

    def test_delete_nonexistent_calculation(self):
        dataset_id = self._post_file()
        result = json.loads(self.controller.delete(dataset_id, self.name))

        self.assertTrue(Calculations.ERROR in result)

    def test_delete(self):
        self._post_formula()
        result = json.loads(self.controller.delete(self.dataset_id, self.name))

        self.assertTrue(AbstractController.SUCCESS in result)

        dataset = Dataset.find_one(self.dataset_id)

        self.assertTrue(self.name not in dataset.schema.labels_to_slugs)

    def test_show_jsonp(self):
        self._post_formula()
        results = self.controller.show(self.dataset_id, callback='jsonp')

        self.assertEqual('jsonp(', results[0:6])
        self.assertEqual(')', results[-1])

    def test_create_aggregation(self):
        self.formula = 'sum(amount)'
        self.name = 'test'
        response = json.loads(self._post_formula())

        self.assertTrue(isinstance(response, dict))
        self.assertTrue(self.controller.SUCCESS in response)
        self.assertTrue(self.dataset_id in response[self.controller.SUCCESS])

        dataset = Dataset.find_one(self.dataset_id)

        self.assertTrue('' in dataset.aggregated_datasets_dict.keys())

    def test_delete_aggregation(self):
        self.formula = 'sum(amount)'
        self.name = 'test'
        response = json.loads(self._post_formula())
        result = json.loads(
            self.controller.delete(self.dataset_id, self.name, ''))

        self.assertTrue(AbstractController.SUCCESS in result)

        dataset = Dataset.find_one(self.dataset_id)
        agg_dataset = Dataset.find_one(dataset.aggregated_datasets_dict[''])

        self.assertTrue(self.name not in agg_dataset.schema.labels_to_slugs)

    def test_error_on_delete_calculation_with_dependency(self):
        self._post_formula()
        dep_name = self.name
        self.formula = dep_name
        self.name = 'test1'
        response = json.loads(self._post_formula())

        self.assertTrue(isinstance(response, dict))
        self.assertTrue(self.controller.SUCCESS in response)

        result = json.loads(
            self.controller.delete(self.dataset_id, dep_name, ''))

        self.assertTrue(AbstractController.ERROR in result)
        self.assertTrue('depend' in result[AbstractController.ERROR])

    def test_create_multiple(self):
        self.dataset_id = self._post_file()
        self._test_create_from_json(
            'good_eats.calculations.json', non_agg_cols=2, ex_len=2)

    def test_create_multiple_ignore_group(self):
        self.dataset_id = self._post_file()
        dataset = self._test_create_from_json(
            'good_eats.calculations.json', non_agg_cols=2, ex_len=2,
            group='risk_factor')

        self.assertEqual(dataset.aggregated_datasets_dict, {})

    def test_create_json_single(self):
        self.dataset_id = self._post_file()
        self._test_create_from_json('good_eats_single.calculations.json')

    def test_create_multiple_with_group(self):
        self.dataset_id = self._post_file()
        group = 'risk_factor'
        dataset = self._test_create_from_json(
            'good_eats_group.calculations.json',
            non_agg_cols=2, ex_len=3, group=group)

        self.assertTrue(group in dataset.aggregated_datasets_dict.keys())

    def test_create_with_missing_args(self):
        self.dataset_id = self._post_file()
        self._test_error(self.controller.create(self.dataset_id))
        self._test_error(
            self.controller.create(self.dataset_id, formula='gps_alt'))
        self._test_error(
            self.controller.create(self.dataset_id, name='test'))

    def test_create_with_bad_json(self):
        self.dataset_id = self._post_file()
        json_filepath = self._fixture_path_prefix(
            'good_eats_bad.calculations.json')
        mock_uploaded_file = self._file_mock(json_filepath)

        self._test_error(
            self.controller.create(self.dataset_id,
                                   json_file=mock_uploaded_file),
            error_text='Required')

        # Mock is now an empty file
        self._test_error(
            self.controller.create(self.dataset_id,
                                   json_file=mock_uploaded_file),
            error_text='No JSON')

    def test_create_reserved_name(self):
        name = 'sum'
        response = json.loads(self._post_formula(None, name))

        self.assertTrue(isinstance(response, dict))
        self.assertTrue(self.controller.SUCCESS in response)
        self.assertTrue(self.dataset_id in response[self.controller.SUCCESS])

        dataset = Dataset.find_one(self.dataset_id)
        slug = dataset.schema.labels_to_slugs[name]
        response = json.loads(self._post_formula('%s + amount' % slug))

        self.assertTrue(isinstance(response, dict))
        self.assertTrue(self.controller.SUCCESS in response)
        self.assertTrue(self.dataset_id in response[self.controller.SUCCESS])

    def test_create_dataset_with_duplicate_column_names(self):
        formula_names = [
            'protected_waterpoint'  # an already slug column
            'protected/waterpoint'  # a non-slug column
            'region'                # an existing column
            'sum'                   # a reserved key
            'date'                  # a reserved key and an existing column
        ]

        for formula_name in formula_names:
            dataset_id = self._post_file('water_points.csv')
            dframe_before = Dataset.find_one(dataset_id).dframe()

            response = json.loads(self.controller.create(
                dataset_id,
                'water_source_type in ["borehole"]',
                formula_name))

            self.assertTrue(isinstance(response, dict))
            self.assertTrue(self.controller.SUCCESS in response)

            dataset = Dataset.find_one(dataset_id)
            dframe_after = dataset.dframe()
            slug = dataset.schema.labels_to_slugs[formula_name]

            self.assertEqual(len(dframe_before), len(dframe_after))
            self.assertTrue(slug not in dframe_before.columns)
            self.assertTrue(slug in dframe_after.columns)
            self.assertEqual(
                len(dframe_before.columns) + 1, len(dframe_after.columns))
