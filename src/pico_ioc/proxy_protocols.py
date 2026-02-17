from .exceptions import SerializationError


class _ProxyProtocolMixin:
    __slots__ = ()

    def __str__(self):
        return str(self._get_real_object())

    def __repr__(self):
        return repr(self._get_real_object())

    def __dir__(self):
        return dir(self._get_real_object())

    def __len__(self):
        return len(self._get_real_object())

    def __getitem__(self, key):
        return self._get_real_object()[key]

    def __setitem__(self, key, value):
        self._get_real_object()[key] = value

    def __delitem__(self, key):
        del self._get_real_object()[key]

    def __iter__(self):
        return iter(self._get_real_object())

    def __reversed__(self):
        return reversed(self._get_real_object())

    def __contains__(self, item):
        return item in self._get_real_object()

    def __add__(self, other):
        return self._get_real_object() + other

    def __sub__(self, other):
        return self._get_real_object() - other

    def __mul__(self, other):
        return self._get_real_object() * other

    def __matmul__(self, other):
        return self._get_real_object() @ other

    def __truediv__(self, other):
        return self._get_real_object() / other

    def __floordiv__(self, other):
        return self._get_real_object() // other

    def __mod__(self, other):
        return self._get_real_object() % other

    def __divmod__(self, other):
        return divmod(self._get_real_object(), other)

    def __pow__(self, other, modulo=None):
        return pow(self._get_real_object(), other, modulo)

    def __lshift__(self, other):
        return self._get_real_object() << other

    def __rshift__(self, other):
        return self._get_real_object() >> other

    def __and__(self, other):
        return self._get_real_object() & other

    def __xor__(self, other):
        return self._get_real_object() ^ other

    def __or__(self, other):
        return self._get_real_object() | other

    def __radd__(self, other):
        return other + self._get_real_object()

    def __rsub__(self, other):
        return other - self._get_real_object()

    def __rmul__(self, other):
        return other * self._get_real_object()

    def __rmatmul__(self, other):
        return other @ self._get_real_object()

    def __rtruediv__(self, other):
        return other / self._get_real_object()

    def __rfloordiv__(self, other):
        return other // self._get_real_object()

    def __rmod__(self, other):
        return other % self._get_real_object()

    def __rdivmod__(self, other):
        return divmod(other, self._get_real_object())

    def __rpow__(self, other):
        return pow(other, self._get_real_object())

    def __rlshift__(self, other):
        return other << self._get_real_object()

    def __rrshift__(self, other):
        return other >> self._get_real_object()

    def __rand__(self, other):
        return other & self._get_real_object()

    def __rxor__(self, other):
        return other ^ self._get_real_object()

    def __ror__(self, other):
        return other | self._get_real_object()

    def __neg__(self):
        return -self._get_real_object()

    def __pos__(self):
        return +self._get_real_object()

    def __abs__(self):
        return abs(self._get_real_object())

    def __invert__(self):
        return ~self._get_real_object()

    def __eq__(self, other):
        return self._get_real_object() == other

    def __ne__(self, other):
        return self._get_real_object() != other

    def __lt__(self, other):
        return self._get_real_object() < other

    def __le__(self, other):
        return self._get_real_object() <= other

    def __gt__(self, other):
        return self._get_real_object() > other

    def __ge__(self, other):
        return self._get_real_object() >= other

    def __hash__(self):
        return hash(self._get_real_object())

    def __bool__(self):
        return bool(self._get_real_object())

    def __call__(self, *args, **kwargs):
        return self._get_real_object()(*args, **kwargs)

    def __enter__(self):
        return self._get_real_object().__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._get_real_object().__exit__(exc_type, exc_val, exc_tb)

    def __reduce_ex__(self, protocol):
        o = self._get_real_object()
        try:
            return o.__reduce_ex__(protocol)
        except Exception as e:
            raise SerializationError(f"Proxy target is not serializable: {e}")
