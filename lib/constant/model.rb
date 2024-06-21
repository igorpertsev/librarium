# frozen_string_literal: true

module Constant
  class Model
    def initialize(constant_hash = {})
      @constant_hash = constant_hash.deep_symbolize_keys.freeze
    end

    def deep_transform
      tap { constant_hash.each { |key, value| define_singleton_method(key) { initialize_value(value) } } }
    end

    delegate_missing_to :constant_hash

    private

    attr_reader :constant_hash

    def initialize_value(value)
      case value
      when Hash then Model.new(value).deep_transform
      when Array then Model.new(value.index_by(&:itself)).deep_transform
      else value.freeze
      end
    end
  end
end
