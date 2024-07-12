class ApplicationController < ActionController::Base
  include LocalizationSupport

  protect_from_forgery with: :exception
end
