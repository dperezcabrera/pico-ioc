from typing import Annotated, Any, Collection, Deque, Dict, Iterable, List, Mapping, Protocol, Sequence, Set, Type, cast

import pytest

from pico_ioc import DependencyRequest, Qualifier, analyze_callable_dependencies, component, factory, init, provides


class IService(Protocol):
    def serve(self) -> str: ...


@component(name="serviceA", qualifiers=["q1"])
class ServiceA(IService):
    def serve(self) -> str:
        return "A"


@component(name="serviceB", qualifiers=["q2"])
class ServiceB(IService):
    def serve(self) -> str:
        return "B"


@component
class OtherComponent:
    pass


@component
class Consumer:
    def __init__(
        self,
        all_services_list: List[IService],
        all_services_set: Set[IService],
        all_services_iterable: Iterable[IService],
        str_map: Dict[str, IService],
        type_map: Dict[Type, IService],
        q1_list: Annotated[List[IService], Qualifier("q1")],
        others: List[OtherComponent],
    ):
        self.all_services_list = all_services_list
        self.all_services_set = all_services_set
        self.all_services_iterable = all_services_iterable
        self.str_map = str_map
        self.type_map = type_map
        self.q1_list = q1_list
        self.others = others


def test_analyze_collections_and_dicts():
    class Sample:
        def __init__(
            self,
            a: List[IService],
            b: Set[IService],
            c: Iterable[IService],
            d: Deque[IService],
            e: Dict[str, IService],
            f: Mapping[Type, IService],
            g: Annotated[List[IService], Qualifier("q")],
            h: Sequence[IService],
            i: Collection[IService],
        ):
            pass

    plan = analyze_callable_dependencies(Sample.__init__)

    assert len(plan) == 9

    assert plan[0].parameter_name == "a"
    assert plan[0].key == IService
    assert plan[0].is_list is True
    assert plan[0].is_dict is False

    assert plan[1].parameter_name == "b"
    assert plan[1].key == IService
    assert plan[1].is_list is True
    assert plan[1].is_dict is False

    assert plan[2].parameter_name == "c"
    assert plan[2].key == IService
    assert plan[2].is_list is True

    assert plan[3].parameter_name == "d"
    assert plan[3].key == IService
    assert plan[3].is_list is True

    assert plan[4].parameter_name == "e"
    assert plan[4].key == IService
    assert plan[4].is_list is False
    assert plan[4].is_dict is True
    assert plan[4].dict_key_type == str

    assert plan[5].parameter_name == "f"
    assert plan[5].key == IService
    assert plan[5].is_list is False
    assert plan[5].is_dict is True
    assert plan[5].dict_key_type == Type

    assert plan[6].parameter_name == "g"
    assert plan[6].key == IService
    assert plan[6].is_list is True
    assert plan[6].qualifier == "q"

    assert plan[7].parameter_name == "h"
    assert plan[7].key == IService
    assert plan[7].is_list is True

    assert plan[8].parameter_name == "i"
    assert plan[8].key == IService
    assert plan[8].is_list is True


def test_container_resolves_collections_and_dicts():

    container = init(modules=[__name__])
    consumer = container.get(Consumer)

    instance_a = container.get("serviceA")
    instance_b = container.get("serviceB")

    instance_other = container.get(OtherComponent)

    assert isinstance(consumer.all_services_list, list)
    assert len(consumer.all_services_list) == 2
    assert instance_a in consumer.all_services_list
    assert instance_b in consumer.all_services_list

    assert isinstance(consumer.all_services_set, list)
    assert len(consumer.all_services_set) == 2
    assert instance_a in consumer.all_services_set
    assert instance_b in consumer.all_services_set

    assert isinstance(consumer.all_services_iterable, list)
    assert len(consumer.all_services_iterable) == 2

    assert isinstance(consumer.str_map, dict)
    assert len(consumer.str_map) == 2
    assert consumer.str_map["serviceA"] is instance_a
    assert consumer.str_map["serviceB"] is instance_b

    assert isinstance(consumer.type_map, dict)
    assert len(consumer.type_map) == 2
    assert consumer.type_map[ServiceA] is instance_a
    assert consumer.type_map[ServiceB] is instance_b

    assert isinstance(consumer.q1_list, list)
    assert len(consumer.q1_list) == 1
    assert consumer.q1_list[0] is instance_a

    assert isinstance(consumer.others, list)
    assert len(consumer.others) == 1
    assert consumer.others[0] is instance_other
