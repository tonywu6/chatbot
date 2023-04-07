from typing import Union

from discord import Colour


class Color2(Colour):
    """Inherits from and replaces :class:`discord.Colour`.

    Supports casting to :class:`int`.

    .. warning::
        :class:`Color2` objects are **immutable**. Attempting to set its
        ``value`` raises :exc:`NotImplementedError`.
    """

    __slots__ = ("_value",)

    def __init__(self, value: Union[int, "Color2"]):
        """Create a :class:`Color2` object.

        .. note::
            :class:`Color2` **accepts any object that can be cast to an**
            :class:`int`, **which includes** :class:`Color2` **itself.**

            This means it is safe to pass a :class:`Color2` object to the
            constructor: ``Color2(Color2(0))`` returns a new ``Color2(0)``
            instance instead of throwing an exception.
        """
        self._value = int(value)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        raise NotImplementedError(f"{type(self).__name__} is immutable.")

    def __getstate__(self):
        return {"_value": self._value}

    def __setstate__(self, d):
        self._value = d["_value"]

    def __index__(self):
        """Return the underlying ``value`` as an :class:`int`.

        .. note::
            :class:`Color2` **objects can be cast to** :class:`int`
            **via** ``int(Color2(...))``, as well as passed to built-in
            methods that accept integers such as :class:`float`, :func:`bin`,
            and :func:`hex`.
        """
        return self.value

    __int__ = __index__

    def __hash__(self):
        """Return a hash for this :class:`Color2`.

        Returns ``hash((type(self), self.value, 37))``.

        .. note::
            In discord.py's implementation of :class:`discord.Colour`
            (as of v1.7.3), for a ``Colour c``, ``hash(c)`` returns
            ``hash(c.value)``, which means **the hash of a**
            :class:`discord.Colour` **object will collide with the hash of
            its underlying value:**

            Both ``0`` and ``Color(0)`` can still coexist in a :class:`dict`,
            however, to ensure that they can coexist, Python must resolve the
            collision by calling :meth:`__eq__` to determine that they are
            not equal.

            This function avoids such a pitfall by including the type object in
            hash calculation.
        """
        return hash((type(self), self.value, 37))

    def __eq__(self, other):
        """Return :data:`True` if the other :class:`Color2` has the same color\
        value as this one.

        Implements the ``==`` operator.

        .. note::
            ``==`` **and** ``!=`` **returns** :data:`NotImplemented` **instead
            of raising** :exc:`TypeError` **for unsupported types.** This means:

            #. :class:`Color2` objects will test unequal against all
               non-:class:`Colour` objects.
            #. If the other object implements ``__eq__``/``__ne__`` and also
               implements logic to compare with :class:`Color2` that does not
               return :data:`NotImplemented`, Python will use that return
               value instead.
        """
        if not isinstance(other, Colour):
            return NotImplemented
        return self.value == other.value

    def __ne__(self, other):
        """Return :data:`True` if the other :class:`Color2` is a different\
        color value than this one.

        Implements the ``!=`` operator.
        """
        # Ideally, we should not define __ne__ and allow Python to
        # delegate to __eq__ which also handles NotImplemented.
        if not isinstance(other, Colour):
            return NotImplemented
        return self.value != other.value
