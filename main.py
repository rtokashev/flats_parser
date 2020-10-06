import abc
import json
import typing
# import logging

import typing_extensions
import requests
import lxml.html

DEFAULT_TIMEOUT = 60


# logging.basicConfig(
#     level=logging.INFO,
#     format='{"level": "%(levelname)s", "name": "%(name)s", "msg": "%(message)s", time":"%(asctime)s"}',
#     datefmt='%Y-%m-%dT%H:%M:%S'
# )


class ResponseSchema(typing_extensions.TypedDict, total=False):
    complex: str
    type: str
    phase: typing.Optional[str]
    building: typing.Optional[str]
    section: typing.Optional[str]
    price: typing.Optional[float]  # deprecated
    price_base: typing.Optional[float]
    price_finished: typing.Optional[float]
    price_sale: typing.Optional[float]
    price_finished_sale: typing.Optional[float]
    area: typing.Optional[float]
    living_area: typing.Optional[float]
    number: typing.Optional[str]
    number_on_site: typing.Optional[str]
    rooms: typing.Optional[typing.Union[int, str]]  # int or 'studio' str
    floor: typing.Optional[int]
    in_sale: typing.Optional[int]
    sale_status: typing.Optional[str]
    finished: typing.Optional[typing.Union[int, str]]
    currency: typing.Optional[str]
    ceil: typing.Optional[float]
    article: typing.Optional[str]
    finishing_name: typing.Optional[str]
    furniture: typing.Optional[int]
    furniture_price: typing.Optional[float]
    plan: typing.Optional[str]
    feature: typing.Optional[typing.List[str]]
    view: typing.Optional[typing.List[str]]
    euro_planning: typing.Optional[int]
    sale: typing.Optional[typing.List[str]]
    discount_percent: typing.Optional[int]
    discount: typing.Optional[float]
    comment: typing.Optional[str]


class DomodedovoGradABC(abc.ABC):
    def __init__(self):
        self.session = requests.Session()

    @abc.abstractmethod
    def collect(self, *args):
        ...


class DomodedovoGradUrlsParser(DomodedovoGradABC):
    def __init__(self):
        super().__init__()
        self.base_url = 'https://www.domodedovograd.ru/domodedovo?grp=242602&page='  # grp query param is hardcoded

    @staticmethod
    def __parse_flats_urls_on_page(page_source: str) -> typing.List[str]:
        tree = lxml.html.fromstring(page_source)
        cards = tree.xpath('.//a[@class="product-card"]/@href')
        return cards

    def __get_flats_amount(self) -> int:
        retries = 3
        while retries:
            retries -= 1
            try:
                smart_filter_form = self.session.get(
                    'https://www.domodedovograd.ru/ajax/GetSmartFilterForm.json?grp=242602&grp=242602&page=1',
                    timeout=DEFAULT_TIMEOUT
                )
            except requests.Timeout:
                continue

            if smart_filter_form.status_code != 200:
                return 0

            text = smart_filter_form.text
            try:
                json_obj = json.loads(text)
            except json.JSONDecodeError as e:
                # print(e)  # raise some error
                return 0
            else:
                return json_obj['prodCount']

    def __get_count_per_page(self) -> int:
        first_page_url = self.base_url + '1'
        response = self.session.get(first_page_url, timeout=DEFAULT_TIMEOUT)

        if response.status_code != 200:
            return 0

        text = response.text
        flats_count_on_first_page = len(self.__parse_flats_urls_on_page(text))
        return flats_count_on_first_page

    @staticmethod
    def _calculate_paging(flats_amount: int, flats_per_page: int) -> int:
        """
        this method is calculate of total pages count
        :return:
        """
        if not flats_amount or not flats_per_page:
            return 0

        if flats_amount % flats_per_page == 0:
            return flats_amount // flats_per_page
        return (flats_amount // flats_per_page) + 1

    def get_flats_urls(self, pages_urls: typing.List[str]):
        result = []
        for page_url in pages_urls:
            retries = 3
            while retries:
                retries -= 1
                response = self.session.get(page_url, timeout=DEFAULT_TIMEOUT)
                if response.status_code == 200:
                    flats_urls = self.__parse_flats_urls_on_page(response.text)
                    result.extend(flats_urls)
        return set(result)

    def collect(self) -> typing.Set[str]:
        flats_amount = self.__get_flats_amount()
        flats_per_page = self.__get_count_per_page()
        total = self._calculate_paging(flats_amount, flats_per_page)
        # logging.info(f'Total pages count {total}: flats amount - {flats_amount}, flats per page - {flats_per_page}')
        pages_urls = [self.base_url + str(page_num) for page_num in range(1, total + 1)]
        res = self.get_flats_urls(pages_urls)

        if len(res) != flats_amount:
            return set()  # or raise some error
        return res


class DomodedovoGradFlatsParser(DomodedovoGradABC):
    def __init__(self):
        super().__init__()
        self.url_adapter = 'https://www.domodedovograd.ru/'

    def get_plan_images(self, url) -> typing.Optional[typing.List[dict]]:
        response = self.session.get(url, timeout=DEFAULT_TIMEOUT)
        if response.status_code == 200:
            return response.json()

    def parse_flat_page(self, page_text: str) -> ResponseSchema:
        complex_ = "Домодедово парк(Московская область, г.Домодедово, с.Домодедово, ул.Творчества)"
        type_ = 'flat'

        tree = lxml.html.fromstring(page_text)
        flat_type = tree.xpath('.//span[@class="breadcrumbs__item"]/text()')[0]
        is_reserved = tree.xpath('.//span[@class="badge badge--secondary"]')

        params_dl = tree.xpath('.//dl[@class="spec mb-30"]/dd/span/text()')
        building = params_dl[0]
        section = params_dl[1]
        floor = params_dl[2]
        number = params_dl[3]
        rooms = int(params_dl[4]) if 'Студия' not in flat_type else 'studio'
        area = living_area = float(str(params_dl[5]).replace(',', '.'))
        phase = params_dl[6]
        sale_status = 'Забронировано' if is_reserved else None
        in_sale = True

        price_finished = str(tree.xpath('.//div[@class="m-passport-price-bar__price"]/text()')[0])
        price_finished = float(''.join([char for char in price_finished if char.isdigit()]))

        number_on_site = str(tree.xpath('//comment()')[0])
        number_on_site = ''.join([char for char in number_on_site if char.isdigit()])

        plan_data_url = '/flat-images.json?flatId=' + number_on_site
        plan_images = self.get_plan_images(self.url_adapter + plan_data_url.strip('/'))
        if plan_images:
            plan = str(plan_images[0].get("sm"))
            plan = self.url_adapter + plan.strip('/')
        else:
            plan = None

        return ResponseSchema(
            complex=complex_,
            type=type_,
            building=building,
            section=section,
            floor=floor,
            number=number,
            number_on_site=number_on_site,
            rooms=rooms,
            area=area,
            living_area=living_area,
            phase=phase,
            plan=plan,
            price_finished=price_finished,
            sale_status=sale_status,
            in_sale=in_sale,
            finished=1
        )

    def get_flat_page(self, flat_url: str) -> str:
        retries = 3
        while retries:
            retries -= 1
            try:
                response = self.session.get(self.url_adapter + flat_url, timeout=DEFAULT_TIMEOUT)
            except requests.Timeout:
                pass
            else:
                if response.status_code == 200:
                    return response.text

    def collect(self, flats_urls: typing.Set[str]) -> str:
        result: typing.List[ResponseSchema] = []
        # logging.info(f'Started parsing of {len(flats_urls)} urls count')
        for flat_url in flats_urls:
            try:
                page_text = self.get_flat_page(flat_url)
            except Exception as e:
                # logging.error(e)
                pass
            else:
                result.append(self.parse_flat_page(page_text))
        # logging.info(f'Parsing of {len(flats_urls)} urls is over')
        return json.dumps(result, ensure_ascii=False)


def main():
    flats_urls_parser = DomodedovoGradUrlsParser()
    flats_parser = DomodedovoGradFlatsParser()
    flats_urls = flats_urls_parser.collect()
    # flats_urls = {'/domodedovo/corpus-8/section-2/floor-2/flat-101',}
    flats_info_json = flats_parser.collect(flats_urls)
    print(flats_info_json)  # sys.stdout by default
    return flats_info_json


if __name__ == '__main__':
    main()
