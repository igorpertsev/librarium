class Settings
  include Singleton

  attr_reader :instagram

  private

  def initialize
    @instagram = ENV.fetch('INSTAGRAM_URL') { 'https://www.instagram.com/littledragonbooks' }
  end
end
