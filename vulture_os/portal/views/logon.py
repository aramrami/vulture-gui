#!/usr/bin/python
#-*- coding: utf-8 -*-
"""This file is part of Vulture 3.

Vulture 3 is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Vulture 3 is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Vulture 3.  If not, see http://www.gnu.org/licenses/.
"""
__author__ = "Kevin Guillemot"
__credits__ = []
__license__ = "GPLv3"
__version__ = "4.0.0"
__maintainer__ = "Vulture OS"
__email__ = "contact@vultureproject.org"
__doc__ = 'Django view used to handle authentication and SSO'


# MONGO IMPORT REQUIRED
from sys import path
path.append("/home/vlt-os/vulture_os/portal")

# Django system imports
from django.conf                     import settings
from django.http                     import HttpResponseRedirect, HttpResponseServerError, HttpResponseForbidden

# Django project imports
from system.cluster.models           import Cluster
from portal.views.responses          import response_redirect_with_portal_cookie, set_portal_cookie
from portal.system.authentications   import (Authentication, POSTAuthentication, BASICAuthentication,
                                             KERBEROSAuthentication, DOUBLEAuthentication)
from portal.system.sso_forwards      import SSOForwardPOST, SSOForwardBASIC, SSOForwardKERBEROS
from workflow.models import Workflow

# Required exceptions imports
from bson.errors                     import InvalidId
from django.core.exceptions          import ValidationError
from django.utils.datastructures     import MultiValueDictKeyError
from ldap                            import LDAPError
from OpenSSL.SSL                     import Error as OpenSSLError
from pymongo.errors                  import PyMongoError
from redis                           import ConnectionError as RedisConnectionError
from requests.exceptions             import ConnectionError as RequestsConnectionError
from sqlalchemy.exc                  import DBAPIError
from portal.system.exceptions        import (TokenNotFoundError, RedirectionNeededError, CredentialsMissingError,
                                             CredentialsError, REDISWriteError, TwoManyOTPAuthFailure, ACLError)
from toolkit.auth.exceptions import AuthenticationError, OTPError

# Extern modules imports

# Logger configuration imports
import logging
logging.config.dictConfig(settings.LOG_SETTINGS)
logger = logging.getLogger('portal_authentication')


def log_in(request, workflow_id=None):
    """ Handle authentication in Vulture Portal
    :param request: Django request object
    :returns: Home page if user auth succeed. Logon page if auth failed
    """
    """ First, try to retrieve concerned objects """
    try:
        workflow = Workflow.objects.get(pk=workflow_id)
    except Exception as e:
        logger.exception(e)
        return HttpResponseForbidden("Injection detected.")

    authentication_classes = {'form':POSTAuthentication, 'basic':BASICAuthentication, 'kerberos':KERBEROSAuthentication}

    global_config = Cluster.get_global_config()

    """ Retrieve token and cookies to instantiate Redis wrapper objects """
    # Retrieve cookies required for authentication
    portal_cookie_name = global_config.portal_cookie_name
    token_name         = global_config.public_token
    portal_cookie      = request.COOKIES.get(portal_cookie_name, None)
    try:
        # Instantiate authentication object to retrieve application auth_type 
        authentication = Authentication(portal_cookie, token_name, workflow)
        # And then instantiate the right authentication class with auth_type ('form','basic','kerberos')
        authentication = authentication_classes[authentication.workflow.authentication.auth_type](portal_cookie,
                                                                                                  token_name, workflow)
        logger.debug("PORTAL::log_in: Authentication successfully created")

    # Application does not need authentication
    except RedirectionNeededError as e:
        logger.error("PORTAL::log_in: {}".format(str(e)))
        return HttpResponseRedirect(e.redirect_url)

    # Redis connection error
    except RedisConnectionError as e:
        logger.error("PORTAL::log_in: Unable to connect to Redis server : {}".format(str(e)))
        return HttpResponseServerError()

    # Token not found while instantiating RedisSession or RedisAppSession
    except TokenNotFoundError as e:
        logger.error("PORTAL::log_in: {}".format(str(e)))

        # Redirect to the same uri, to stock token in Redis via session filter
        return HttpResponseRedirect("")

    # If redis_session.keys['application_id'] does not exists : FORBIDDEN
    except (Workflow.DoesNotExist, ValidationError, InvalidId) as e:
        logger.error("PORTAL::log_in: Application with id '{}' not found"
                     .format(authentication.redis_session.keys.get('application_id')))
        return HttpResponseForbidden()

    # If assertionError : Ask credentials by portal
    except AssertionError as e:
        logger.error("PORTAL::log_in: AssertionError while trying to create Authentication : ".format(e))
        return authentication.ask_credentials_response(request=request)


    """ If user is not authenticated : try to retrieve credentials and authenticate him on backend/fallback-backends """
    # If the user is not authenticated and application need authentication
    if not authentication.is_authenticated():
        try:
            backend_id = authentication.authenticate_sso_acls()
            if not backend_id:
                # Retrieve credentials
                authentication.retrieve_credentials(request)
                logger.debug("PORTAL::log_in: Credentials successfully retrieved")

                # Authenticate user with credentials retrieven
                authentication_results = authentication.authenticate(request)
                logger.debug("PORTAL::log_in: Authentication succeed on backend {}".format(authentication.backend_id))

                # Register authentication results in Redis
                portal_cookie, oauth2_token = authentication.register_user(authentication_results)
                logger.debug("PORTAL::log_in: User {} successfully registered in Redis".format(authentication.credentials[0]))

                if authentication_results['data'].get('password_expired', None):
                    logger.info("PORTAL::log_in: User '{}' must change its password, redirect to self-service portal"
                                .format(authentication.credentials[0]))
                    # FIXME : See w/ JJO for application.auth_portal & get_redirect_uri
                    app_url = authentication.get_url_portal()
                    return response_redirect_with_portal_cookie(app_url+str(token_name)+'/self/change',
                                                                portal_cookie_name,
                                                                portal_cookie,
                                                                app_url.startswith('https'), None)
            # If the user is already authenticated (retrieven with RedisPortalSession ) => SSO
            else:
                portal_cookie, oauth2_token = authentication.register_sso(backend_id)
                logger.info("PORTAL::log_in: User {} successfully SSO-powered !".format(authentication.credentials[0]))

        except AssertionError as e:
            logger.error("PORTAL::log_in: Bad captcha taped for username '{}' : {}"
                         .format(authentication.credentials[0], e))
            return authentication.ask_credentials_response(request=request, error="Bad captcha")

        except AuthenticationError as e:
            logger.error("PORTAL::log_in: AuthenticationError while trying to authenticate user '{}' : {}"
                         .format(authentication.credentials[0], e))
            return authentication.ask_credentials_response(request=request, error="Bad credentials")

        except ACLError as e:
            logger.error("PORTAL::log_in: ACLError while trying to authenticate user '{}' : {}"
                         .format(authentication.credentials[0], e))
            return authentication.ask_credentials_response(request=request, error="Not authorized")

        except (DBAPIError, PyMongoError, LDAPError) as e:
            logger.error("PORTAL::log_in: Repository driver Error while trying to authentication user '{}' : {}"
                         .format(authentication.credentials[0], e))
            return authentication.ask_credentials_response(request=request,
                                                           error="Connection to repository failed <br> "
                                                                 "<b> Contact your administrator </b>")

        except (MultiValueDictKeyError, AttributeError, KeyError) as e:
            # vltprtlsrnm is always empty during the initial redirection. Don't log that
            logger.error("PORTAL::log_in: Error while trying to authentication user '{}' : {}"
                         .format(authentication.credentials[0], e))
            return authentication.ask_credentials_response(request=request)

        except REDISWriteError as e:
            logger.error("PORTAL::log_in: RedisWriteError while trying to register user '{}' informations : {}"
                         .format(authentication.credentials[0], e))
            return HttpResponseServerError()

        except Exception as e:
            logger.error("ERROR !")
            logger.exception(e)
            return HttpResponseServerError()


    """ If user is not double-authenticated and double-authentication needed : 
            try to retrieve credentials and authenticate him on otp-backend 
    """
    # If the user is authenticated but not double-authenticated and double-authentication required
    if authentication.double_authentication_required():
        logger.info("PORTAL::log_in: Double authentication required for user {}".format(authentication.credentials[0]))
        try:
            # Instantiate DOUBLEAuthentication object
            db_authentication = DOUBLEAuthentication(portal_cookie)
            logger.debug("PORTAL::log_in: DoubleAuthentication successfully created")
            # And try to retrieve credentials
            db_authentication.retrieve_credentials(request)
            logger.debug("PORTAL::log_in: DoubleAuthentication credentials successfully retrieved")
            # And use them to authenticate user
            db_authentication.authenticate(request)
            logger.info("PORTAL::log_in: User '{}' successfully double authenticated"
                        .format(authentication.credentials[0]))

        except AssertionError as e:
            """ If redis_portal_session does not exists or can't retrieve otp key in redis """
            logger.error("PORTAL::log_in: DoubleAuthentication failure for username '{}' : {}"
                         .format(authentication.credentials[0], str(e)))
            return authentication.ask_credentials_response(request=request, portal_cookie_name=portal_cookie_name,
                                                           error="Portal cookie expired")

        except (Application.DoesNotExist, ValidationError, InvalidId) as e:
            """ Invalid POST 'vulture_two_factors_authentication' value """
            logger.error("PORTAL::log_in: Double-authentication failure for username {} : {}"
                         .format(authentication.credentials[0], str(e)))
            return HttpResponseForbidden("Intrusion attempt blocked")

        except REDISWriteError as e:
            """ Cannot register double-authentication in Redis : internal server error """
            logger.error("PORTAL::log_in: Failed to write double-authentication results in Redis for username '{}' : {}"
                         .format(db_authentication.credentials[0], str(e)))
            return HttpResponseServerError()

        # If authentication failed : create double-authentication key and ask-it
        except CredentialsError as e:
            """ CredentialsError: no OTP credentials provided : ask-them """
            logger.error("PORTAL::log_in: Double-authentication failure for username {} : {}"
                         .format(authentication.credentials[0], str(e)))
            try:
                db_authentication.create_authentication()
                return db_authentication.ask_credentials_response(request=request,
                                                                  portal_cookie_name=portal_cookie_name)

            except (OTPError, REDISWriteError, RedisConnectionError) as e:
                """ Error while sending/registering in Redis the OTP informations : display portal"""
                logger.error("PORTAL::log_in: Failed to create/send double-authentication key : {}".format(str(e)))
                db_authentication.deauthenticate_user()
                logger.info("PORTAL::log_in: User '{}' successfully deauthenticated due to db-authentication error"
                            .format(authentication.credentials[0]))
                return authentication.ask_credentials_response(request=request,
                                                               error="<b> Error sending OTP Key </b> </br> "+str(e))

        except AuthenticationError as e:
            """ Bad OTP key """
            logger.error("PORTAL::log_in: DoubleAuthentication failure for username {} : {}"
                         .format(authentication.credentials[0], str(e)))
            try:
                db_authentication.create_authentication()
                db_authentication.authentication_failure()
                logger.debug("PORTAL:log_in: DoubleAuthentication failure successfully registered in Redis")
                return db_authentication.ask_credentials_response(request=request,
                                                                  portal_cookie_name=portal_cookie_name,
                                                                  error="<b> Bad OTP key </b>")

            except TwoManyOTPAuthFailure as e:
                logger.error("PORTAL::log_in: Two many OTP authentication failures for username'{}', "
                             "redirecting to portal".format(authentication.credentials[0]))
                db_authentication.deauthenticate_user()
                logger.info("PORTAL::log_in: User '{}' successfully deauthenticated due to db-authentication error"
                            .format(authentication.credentials[0]))
                return authentication.ask_credentials_response(request=request, error=e.message)

            except (OTPError, REDISWriteError, RedisConnectionError) as e:
                logger.error("PORTAL::log_in: Error while preparing double-authentication : {}".format(str(e)))
                return db_authentication.ask_credentials_response(request=request,
                                                                  portal_cookie_name=portal_cookie_name,
                                                                  error="<b> Error sending OTP Key </b> </br> "+str(e))

        except OTPError as e:
            """ OTP Error while authenticating given token """
            logger.error("PORTAL::log_in: Double-authentication failure for username {} : {}"
                         .format(authentication.credentials[0], str(e)))
            return db_authentication.ask_credentials_response(request=request, portal_cookie_name=portal_cookie_name,
                                                              error="<b> OTP Error </b> {}".format(str(e)))

        except TwoManyOTPAuthFailure as e:
            logger.error("PORTAL::log_in: Two many OTP authentication failures for username'{}', "
                         "redirecting to portal".format(authentication.credentials[0]))
            db_authentication.deauthenticate_user()
            logger.info("PORTAL::log_in: User '{}' successfully deauthenticated due to db-authentication error"
                        .format(authentication.credentials[0]))
            return authentication.ask_credentials_response(request=request, error=e.message)

    # If we arrive here : the user is authenticated
    #  and double-authenticated if double-authentication needed
    sso_methods = {
        'form': SSOForwardPOST,
        'basic': SSOForwardBASIC,
        'kerberos': SSOForwardKERBEROS
    }

    """ If SSOForward enabled : perform-it """
    if authentication.application.sso_enabled:
        # Try to retrieve credentials from authentication object 
        try:
            if not authentication.credentials[0] or not authentication.credentials[1]:
                authentication.get_credentials(request)
            # If we cannot retrieve them, ask credentials
            if not authentication.credentials[0]:  # or not authentication.credentials[1]:
                return authentication.ask_credentials_response(request=request, portal_cookie_name=portal_cookie_name,
                                                               error="Credentials not found")
            logger.info("PORTAL::log_in: Credentials successfuly retrieven for SSO performing")

        except Exception as e:
            logger.error("PORTAL::log_in: Error while retrieving credentials for SSO : ")
            logger.exception(e)
            return authentication.ask_credentials_response(request=request, portal_cookie_name=portal_cookie_name,
                                                           error="Credentials not found")

        try:
            # Instantiate SSOForward object with sso_forward type
            sso_forward = sso_methods[authentication.application.sso_forward](request, authentication.application,
                                                                              authentication)
            logger.info("PORTAL::log_in: SSOForward successfully created")
            # Get credentials needed for sso forward : AutoLogon or Learning
            sso_data, profiles_to_stock, url = sso_forward.retrieve_credentials(request)
            logger.info("PORTAL::log_in: SSOForward credentials successfully retrieven")
            # If credentials retrieven needs to be stocked
            for profile_name,profile_value in profiles_to_stock.items():
                sso_forward.stock_sso_field(authentication.credentials[0], profile_name, profile_value)

            # Use 'sso_data' and 'url' to authenticate user on application 
            response = sso_forward.authenticate(sso_data, post_url=url, redis_session=authentication.redis_session)
            logger.info("PORTAL::log_in: SSOForward performing success")
            # Generate response depending on application.sso_forward options
            final_response = sso_forward.generate_response(request, response, authentication.get_redirect_url())
            logger.info("PORTAL::log_in: SSOForward response successfuly generated")

            # If the user has not yet a portal cookie : give-it
            if not request.COOKIES.get(portal_cookie_name, None) or \
                    not authentication.redis_base.hgetall(request.COOKIES.get(portal_cookie_name, None)):
                final_response = set_portal_cookie(final_response, portal_cookie_name, portal_cookie,
                                                   authentication.get_redirect_url())

            return final_response

        # If learning credentials cannot be retrieven : ask them
        except CredentialsMissingError as e:
            logger.error("PORTAL::log_in: Learning credentials missing : asking-them")
            return authentication.ask_learning_credentials(request=request,
                                                           portal_cookie_name=None if request.POST.get(portal_cookie_name, None) else portal_cookie_name,
                                                           fields=e.fields_missing)

        # If KerberosBackend object cannot be retrieven from mongo with the backend_id that the user is authenticated on
        except InvalidId:
            logger.error("PORTAL::log_in: The user is authenticated on a not Kerberos backend, cannot do SSOForward")

        except (RequestsConnectionError,OpenSSLError) as e:
            logger.error("PORTAL::log_in: ConnectionError while trying to SSO to backend : ")
            logger.exception(e)

        except Exception as e:
            logger.error("PORTAL::log_in: Unexpected error while trying to perform SSO Forward :")
            logger.exception(e)

    """ If no response has been returned yet : redirect to the asked-uri/default-uri with portal_cookie """
    redirection_url = authentication.get_redirect_url()
    logger.info("PORTAL::log_in: Redirecting user to '{}'".format(redirection_url))
    try:
        kerberos_token_resp = authentication_results['data']['token_resp']
    except:
        kerberos_token_resp = None
    return response_redirect_with_portal_cookie(redirection_url, portal_cookie_name, portal_cookie,
                                                redirection_url.startswith('https'), kerberos_token_resp)

