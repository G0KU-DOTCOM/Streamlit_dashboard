import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd
import requests

from dashboard.exchange_rates import EXCHANGE_RATE_URL, ExchangeRateError, download_exchange_rates


HEADER = "FREQ;BASE_CUR;QUOTE_CUR;TENOR;UNIT_MULT;TIME_PERIOD;OBS_VALUE\n"
EUR = "B;EUR;NOK;SP;0;2024-12-23;11.807\n"
USD = "B;USD;NOK;SP;0;2024-12-23;11.3605\n"


def response_with(body, status=200):
    response = requests.Response()
    response.status_code = status
    response.url = EXCHANGE_RATE_URL
    response.encoding = "utf-8"
    response._content = body.encode("utf-8")
    return response


class ExchangeRateTests(unittest.TestCase):
    @patch("dashboard.exchange_rates.requests.get")
    def test_returns_sorted_quote_dates_and_keeps_missing_values(self, get):
        get.return_value = response_with(HEADER + "B;EUR;NOK;SP;0;2024-12-27;11.8435\n" + USD + EUR)

        rates = download_exchange_rates(date(2024, 12, 23), "2024-12-29")

        self.assertEqual(list(rates.columns), ["eur_nok", "usd_nok"])
        self.assertEqual(list(rates.index), [pd.Timestamp("2024-12-23"), pd.Timestamp("2024-12-27")])
        self.assertEqual(rates.iloc[0].to_list(), [11.807, 11.3605])
        self.assertTrue(pd.isna(rates.iloc[1]["usd_nok"]))
        self.assertEqual(get.call_args.kwargs["params"]["endPeriod"], "2024-12-29")

    @patch("dashboard.exchange_rates.requests.get")
    def test_empty_responses_get_a_clear_message(self, get):
        for body, status in (("", 200), (HEADER, 200), ("", 204), ("", 404)):
            with self.subTest(body=body, status=status):
                get.return_value = response_with(body, status)
                with self.assertRaisesRegex(ExchangeRateError, "no published exchange rates"):
                    download_exchange_rates("2024-12-28", "2024-12-29")

    @patch("dashboard.exchange_rates.requests.get", side_effect=requests.Timeout)
    def test_reports_a_network_failure(self, _get):
        with self.assertRaisesRegex(ExchangeRateError, "Could not download exchange rates"):
            download_exchange_rates("2024-12-23", "2024-12-29")

    @patch("dashboard.exchange_rates.requests.get")
    def test_rejects_bad_observations(self, get):
        for data, message in (
            (EUR, "both EUR and USD"),
            (EUR + USD + EUR, "duplicate dates"),
            (EUR + USD.replace(";0;", ";2;"), "per unit"),
            (EUR + USD.replace(";11.3605", ";0"), "invalid exchange rate"),
            (EUR + USD.replace("2024-12-23", "2024-12-22"), "outside the requested period"),
        ):
            with self.subTest(message=message):
                get.return_value = response_with(HEADER + data)
                with self.assertRaisesRegex(ExchangeRateError, message):
                    download_exchange_rates("2024-12-23", "2024-12-29")

    @patch("dashboard.exchange_rates.requests.get")
    def test_rejects_reversed_dates_before_contacting_the_api(self, get):
        with self.assertRaisesRegex(ValueError, "start date must be on or before"):
            download_exchange_rates("2024-12-29", "2024-12-23")
        get.assert_not_called()
