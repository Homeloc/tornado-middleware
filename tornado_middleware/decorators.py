import functools
import types

from tornado.gen import ExceptionStackContext, Runner


def _opt_arguments(func):
    ''' Make arguments in decorators fillable with keywords
    '''

    def meta_wrapper(*args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            # No arguments, this is the decorator
            # Set default values for the arguments
            return func(args[0])
        else:
            def meta_func(inner_func):
                return func(inner_func, *args, **kwargs)
            return meta_func
    return meta_wrapper


@_opt_arguments
def callback_engine(func, callback_arg_name='callback'):
    ''' Does the same as tornado.gen.engine, except it automatically
        adds a callback keyword argument, and calls the provided callback
        whenever the function it wraps is done executing, whether it was
        an engine or a regular function.

        It also tolerates being called without the `callback` keyword argument,
        in which case it will behave just like `engine`.

        Example:

        @callback_engine
        def my_function(arg1, arg2):
            something = yield Task(...)

        ...

        yield Task(my_function, arg1, arg2)
        print 'done'
        # 'done' is printed after my_function is completely done.


        :param callback_arg_name: In case you want to call the callback
            something else, just use ;

            @callback_engine(callback_arg_name='done_callback')
            def my_function(*args):
                ...

            ...

            my_function(*args, done_callback=some_callback)
    '''

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        runner = None

        def handle_exception(typ, value, tb):
            # if the function throws an exception before its first "yield"
            # (or is not a generator at all), the Runner won't exist yet.
            # However, in that case we haven't reached anything asynchronous
            # yet, so we can just let the exception propagate.
            if runner is not None:
                return runner.handle_exception(typ, value, tb)
            return False

        # with ExceptionStackContext(handle_exception):
        callback = kwargs.pop(callback_arg_name, None)
        with ExceptionStackContext(handle_exception) as deactivate:
            def _done(*a, **kw):
                deactivate()
                if callback:
                    callback()
            gen = func(*args, **kwargs)

            # If func indeed provided a generator, then run it
            # and have it call _done when it's done
            if isinstance(gen, types.GeneratorType):
                runner = Runner(gen, _done)
                runner.run()
                return

            # If func was a regular function, then it shouldn't
            # return anything. We then call done() to continue
            # in the async chain.
            assert gen is None, gen
            _done()
        return runner

    return wrapper

__all__ = ['callback_engine']
