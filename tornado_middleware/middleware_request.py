from tornado.web import RequestHandler, HTTPError
from tornado.gen import Task
from tornado import stack_context
from decorators import callback_engine


class InterruptRequest(Exception):
    ''' When fired, this exception interrupts completely a request processing,
        not triggering the corresponding get/post method.

        Only the middleware that have been already processed, including the
        one that fired this exception see their .after method called.
    '''


class MiddlewareRequestMeta(type):
    '''
        Wraps get/post/... in callback_engine, and assemble the middleware
        from all the bases of the class.
    '''

    def __new__(metacls, name, bases, dct):
        middleware = dct.get('middleware', [])

        for base in bases:
            base_middleware = getattr(base, 'middleware', [])
            middleware = base_middleware + middleware

        dct['middleware'] = middleware

        for _n in ['get', 'post', 'head', 'put', 'delete']:
            if _n in dct:
                dct[_n] = callback_engine(dct[_n])

        cls = type.__new__(metacls, name, bases, dct)

        return cls


class MiddlewareRequestHandler(RequestHandler):
    '''
        This class effectively renders the asynchronous obsolete, since all
        the get/post/... method will be treated as such by default, whether
        they really trigger an asynchronous call or not.

        The behaviour of redirect() and finish() are slightly different than
        on the tornado.web.RequestHandler class.

        finish is essentially useless ; it will be called anyways after all the
        .after methods of the middleware have been run.
        redirect just delays the redirection for after the .after middleware
        methods.

        The reason for this is that all the middleware *must* be run before
        sending the user anywhere, to avoid any possible race condition that
        could come if the user queries the server before the after middleware
        has been run.

        If you want to run code after finish(), use the after_finish method
        in your middleware.
    '''

    # This metaclass is just to ensure that get/post/delete/etc... are
    # always wrapped in a callback_engine.
    __metaclass__ = MiddlewareRequestMeta

    middleware = []

    def __init__(self, *a, **kw):
        super(MiddlewareRequestHandler, self).__init__(*a, **kw)

        self._called_once = False  # used to check if it is the first time
            # the middleware is being run, and to prevent a re-run in the case
            # that the get() or post() method is being redefined and called
            # with super(klass, self).get(...)

        self._redirection = None
        self._cached_args = None

    def redirect(self, *a, **kw):
        self._redirection = a, kw

    def finish(self):
        ''' this does nothing, see do_finish. '''

    def try_redirect(self):
        if self._redirection:
            a, kw = self._redirection
            super(MiddlewareRequestHandler, self).redirect(*a, **kw)

    def do_finish(self):
        super(MiddlewareRequestHandler, self).finish()

    @callback_engine
    def _execute(self, transforms, *args, **kwargs):
        """
            Executes this request with the given output transforms.
            Also run the middleware.
        """

        with stack_context.ExceptionStackContext(
                self._stack_context_handle_exception):
            self._transforms = transforms

            run_middleware = not self._called_once
            self._called_once = True
            executed_middleware = []

            if run_middleware:
                if self.request.method not in self.SUPPORTED_METHODS:
                    raise HTTPError(405)

                # If XSRF cookies are turned on, reject form submissions without
                # the proper cookie
                if self.request.method not in ('GET', 'HEAD', 'OPTIONS') and \
                   self.application.settings.get("xsrf_cookies"):
                    self.check_xsrf_cookie()

                self.prepare()

            if self._cached_args:
                args, kwargs = self._cached_args
            else:
                args = [self.decode_argument(arg) for arg in args]

                kwargs = dict((k, self.decode_argument(v, name=k))
                              for (k, v) in kwargs.iteritems())
                self._cached_args = args, kwargs

            try:
                if run_middleware:
                    for middle_class in self.__class__.middleware:
                        middle = middle_class(self)
                        executed_middleware.insert(0, middle)
                        yield Task(middle.before, *args, **kwargs)

                # Since all the get/post/... methods are wrapped in
                # callback_engine we call them in a Task, whether they're
                # asynchronous or not.
                yield Task(
                    getattr(self, self.request.method.lower()),
                    *args,
                    **kwargs
                )

            except InterruptRequest:
                pass

            if run_middleware:
                for middle in executed_middleware:
                    yield Task(middle.after, *args, **kwargs)

                # If self.redirect() was called during treatment of the request,
                # this is where it will be effectively called.
                self.try_redirect()
                if not self._finished:
                    # If there was no redirect, then we finish the request, this
                    # time for real.
                    self.do_finish()

                for middle in executed_middleware:
                    yield Task(middle.after_finish, *args, **kwargs)


class MiddlewareMetaclass(type):
    ''' Applies callback_engine on before and after of the middleware.
    '''

    def __new__(metacls, name, bases, dct):

        for method_name in ['before', 'after', 'after_finish']:
            if method_name in dct:
                dct[method_name] = callback_engine(dct[method_name])

        return type.__new__(metacls, name, bases, dct)


class Middleware(object):
    ''' The base Middleware class.
    '''

    __metaclass__ = MiddlewareMetaclass

    def __init__(self, handler):
        '''
        '''

        self.handler = handler

    def before(self, *args, **kwargs):
        ''' Executed just after prepare(), but before get/post/...
        '''

    def after(self, *args, **kwargs):
        ''' Executed right after the end of the get/post/... methods of the
            request handler.

            Called `before` self.finish() or self.redirect().
        '''

    def after_finish(self, *args, **kwargs):
        ''' Executed after finish() of the Request, which means that
            the client has already been redirected, or simply received the end
            of the request.

            Useful for logging.
        '''
