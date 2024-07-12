class Author < ApplicationRecord
  has_many :books
  has_many :genres, through: :books

  validates :full_name, presence: true
  validates :full_name, uniqueness: true
end
