class Genre < ApplicationRecord
  has_many :genres_to_books

  validates :name, presence: true, uniqueness: true
end
